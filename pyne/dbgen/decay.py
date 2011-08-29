"""This module provides a way to grab and store raw data for radioactive decay."""
import os
import re
import urllib2

import numpy as np
import tables as tb

from pyne import nucname
from pyne.dbgen.kaeri import grab_kaeri_nuclide

# Note that since ground state and meta-stable isotopes are of the same atomic weight, 
# the meta-stables have been discluded from the following data sets.

iso_regex = re.compile('.*?/cgi-bin/nuclide[?]nuc=([A-Za-z]{1,2}\d{1,3}).*?')

def parse_for_all_isotopes(htmlfile):
    """Parses an elemental html file, returning a set of all isotopes."""
    isos = set()
    with open(htmlfile, 'r') as f:
        for line in f:
            m = iso_regex.search(line)
            if m is not None:
                isos.add(nucname.zzaaam(m.group(1)))
    return isos


def grab_kaeri_decay(build_dir=""):
    """Grabs the KAERI files needed for the decay data, 
    if not already present.

    Parameters
    ----------
    build_dir : str
        Major directory to place html files in. 'KAERI/' will be appended.
    """
    # Add kaeri to build_dir
    build_dir = os.path.join(build_dir, 'KAERI')
    try:
        os.makedirs(build_dir)
    except OSError:
        pass
    already_grabbed = set(os.listdir(build_dir))

    # Grab and parse elemental summary files.
    nuclides = set()
    for element in nucname.name_zz.keys():
        htmlfile = element + '.html'
        if htmlfile not in already_grabbed:
            grab_kaeri_nuclide(element, build_dir)

        nuclides = nuclides | parse_for_all_isotopes(os.path.join(build_dir, htmlfile))

    # Grab natural nuclide files
    for nuc in nuclides:
        nuc = nucname.name(nuc)
        htmlfile = nuc + '.html'
        if htmlfile not in already_grabbed:
            grab_kaeri_nuclide(nuc, build_dir)



half_life_regex = re.compile('<li>Half life: [~]?(\d+[.]?\d*?)\s*(\w+)')

def parse_decay(build_dir=""):
    """Builds and returns a list of nuclide decay data."""
    build_dir = os.path.join(build_dir, 'KAERI')

    # Grab and parse elemental summary files.
    nuclides = set()
    for element in nucname.name_zz.keys():
        htmlfile = element + '.html'
        nuclides = nuclides | parse_for_all_isotopes(os.path.join(build_dir, htmlfile))

    decay_data = []

    from_nuc_name = ""
    from_nuc_zz = 0
    to_nuc_name = ""
    to_nuc_zz = 0
    hl = 0.0
    dc = 0.0
    br = 1.0

    for nuc in nuclides:
        nuc_name = nucname.name(nuc)
        htmlfile = os.path.join(build_dir, nuc_name + '.html')

        from_nuc_name = nuc_name
        from_nuc_zz = nuc
        br = 1.0

        with open(htmlfile, 'r') as f:
            for line in f:
                m = half_life_regex.search(line)
                if m is not None:
                    val = float(m.group(1)) * 0.01
                    atomic_abund[nuc] = val
                    continue

    return decay_data





atomic_weight_desc = {
    'nuc_name': tb.StringCol(itemsize=6, pos=0),
    'nuc_zz':   tb.IntCol(pos=1),
    'mass':     tb.FloatCol(pos=2),
    'error':    tb.FloatCol(pos=3),
    'abund':    tb.FloatCol(pos=4),
    }

atomic_weight_dtype = np.dtype([
    ('nuc_name', 'S6'),
    ('nuc_zz',   int),
    ('mass',     float),
    ('error',    float), 
    ('abund',    float), 
    ])

def make_atomic_weight_table(nuc_data, build_dir=""):
    """Makes an atomic weight table in the nuc_data library.

    Parameters
    ----------
    nuc_data : str
        Path to nuclide data file.
    build_dir : str
        Directory to place html files in.
    """
    # Grab raw data
    atomic_abund  = parse_atomic_abund(build_dir)
    atomic_masses = parse_atmoic_mass_adjustment(build_dir)

    A = {}

    # Add normal isotopes to A
    for nuc_zz, mass, error in atomic_masses:
        try: 
            nuc_name = nucname.name(nuc_zz)
        except RuntimeError:
            continue

        if nuc_zz in atomic_abund:
            A[nuc_zz] = nuc_name, nuc_zz, mass, error, atomic_abund[nuc_zz]
        else:
            A[nuc_zz] = nuc_name, nuc_zz, mass, error, 0.0

    # Add naturally occuring elements
    for element in nucname.name_zz:
        nuc_zz = nucname.zzaaam(element)
        A[nuc_zz] = element, nuc_zz, 0.0, 0.0, 0.0
        
    for nuc, abund in atomic_abund.items():
        zz = nuc / 10000
        element_zz = zz * 10000
        element = nucname.zz_name[zz]

        nuc_name, nuc_zz, nuc_mass, _error, _abund = A[nuc]
        elem_name, elem_zz, elem_mass, _error, _abund = A[element_zz]

        new_elem_mass = elem_mass + (nuc_mass * abund)
        A[element_zz] = element, element_zz, new_elem_mass, 0.0, 0.0


    A = sorted(A.values(), key=lambda x: x[1])
    #A = np.array(A, dtype=atomic_weight_dtype)

    # Open the HDF5 File
    kdb = tb.openFile(nuc_data, 'a')

    # Make a new the table
    Atable = kdb.createTable("/", "atomic_weight", atomic_weight_desc, 
                             "Atomic Weight Data [amu]", expectedrows=len(A))
    Atable.append(A)

    # Ensure that data was written to table
    Atable.flush()

    # Close the hdf5 file
    kdb.close()




def make_atomic_weight(nuc_data, build_dir):
    with tb.openFile(nuc_data, 'a') as f:
        if hasattr(f.root, 'atomic_weight'):
            return 

    # First grab the atomic abundance data
    print "Grabing the atomic abundance from KAERI"
    grab_kaeri_atomic_abund(build_dir)

    # Then grab mass data
    print "Grabing atomic mass data from AMDC"
    grab_atmoic_mass_adjustment(build_dir)

    # Make atomic weight table once we have the array
    print "Making atomic weight data table."
    make_atomic_weight_table(nuc_data, build_dir)
