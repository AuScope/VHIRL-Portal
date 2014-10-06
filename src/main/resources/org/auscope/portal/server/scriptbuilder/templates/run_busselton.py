"""Script for running a tsunami inundation scenario for Busselton, WA Australia.

Source data such as elevation and boundary data is assumed to be available in
directories specified by project.py
The output sww file is stored in directory named after the scenario, i.e
slide or fixed_wave.

The scenario is defined by a triangular mesh created from project.polygon,
the elevation data and a tsunami wave generated by a submarine mass failure.

Geoscience Australia, 2004-present
"""

"""ANUGA modelling using portal netCDF data"""


#------------------------------------------------------------------------------
# Import necessary modules
#------------------------------------------------------------------------------
# Standard modules
import os
import time
import sys
from math import sin, pi, exp
import numpy as np
import VHIRL_conversions
import subprocess
from os.path import join, exists

# Related major packages
import anuga

######################################################
####### Do not change anything above this line #######

# Definition of file names and polygons
""" Common filenames and locations for topographic data, meshes and outputs.
    This file defines the parameters of the scenario you wish to run.
"""

#------------------------------------------------------------------------------
# Filenames
#------------------------------------------------------------------------------

# Filename for input data (NetCDF format)
dataset = '${input_dataset}'
name_stem = scenario_name = '${name_stem}'
meshname = name_stem + '.msh'

#------------------------------------------------------------------------------
# Runtime parameters
#------------------------------------------------------------------------------
v_cache = False
v_verbose = True

#------------------------------------------------------------------------------
# Define scenario as either slide or fixed_wave. Choose one.
#------------------------------------------------------------------------------
scenario = 'fixed_wave' # Huge wave applied at the boundary


#------------------------------------------------------------------------------
# Domain definitions
#------------------------------------------------------------------------------
# bounding polygon for study area
busselton_extent = np.asarray([[357325,6270510],
                               [344635,6267810],
                               [314645,6268400],
                               [286811,6277911],
                               [286174,6308019],
                               [293089,6341152],
                               [344595,6456235],
                               [389463,6441867],
                               [392955,6320400],
                               [379095,6288910]])

zone = 50
base_scale = ${base_scale}
default_res = 25 * base_scale   # Background resolution

#------------------------------------------------------------------------------
# Data for Tides
#------------------------------------------------------------------------------
v_tide = ${tide}


####### Do not change anything below this line #######
######################################################

jobstart = time.time()


# Create ASC from nc data
VHIRL_conversions.nc2asc(dataset, name_stem, zone=zone)

# Create DEM from asc data
anuga.asc2dem(name_stem+'.asc', use_cache=v_cache, verbose=v_verbose)

# Create pts file for onshore DEM
anuga.dem2pts(name_stem+'.dem', use_cache=v_cache, verbose=v_verbose)

#------------------------------------------------------------------------------
# Create the triangular mesh and domain based on
# overall clipping polygon with a tagged
# boundary and interior regions as defined in project.py
#------------------------------------------------------------------------------
domain = anuga.create_domain_from_regions(busselton_extent,
                                    boundary_tags={'land_sse': [0],
                                                   'land_s': [1],
                                                   'bottom': [2],
                                                   'ocean_wsw': [3],
                                                   'ocean_w': [4],
                                                   'ocean_wnw': [5],
                                                   'top': [6],
                                                   'land_nne': [7],
                                                   'land_ese': [8],
                                                   'land_se': [9]},
                                    maximum_triangle_area=default_res,
                                    mesh_filename=meshname,
                                    use_cache=v_cache,
                                    verbose=v_verbose)

# Print some stats about mesh and domain
print 'Number of triangles = ', len(domain)
print 'The extent is ', domain.get_extent()
print domain.statistics()

#------------------------------------------------------------------------------
# Setup parameters of computational domain
#------------------------------------------------------------------------------
domain.set_name('busselton_' + scenario) 	  # Name of sww file
domain.set_datadir('.')                       # Store sww output here
domain.set_minimum_storable_height(0.01)      # Store only depth > 1cm
domain.set_flow_algorithm('tsunami')



#------------------------------------------------------------------------------
# Setup initial conditions
#------------------------------------------------------------------------------
tide = v_tide
domain.set_quantity('stage', tide)
domain.set_quantity('friction', 0.0)


domain.set_quantity('elevation',
                    filename=name_stem + '.pts',
                    use_cache=v_cache,
                    verbose=v_verbose,
                    alpha=0.1)


bounaryStartTime = time.time()

#------------------------------------------------------------------------------
# Setup boundary conditions
#------------------------------------------------------------------------------
print 'Available boundary tags', domain.get_boundary_tags()

# Mean water level
Bd = anuga.Dirichlet_boundary([tide, 0, 0]) 

# Neutral boundary
Bs = anuga.Transmissive_stage_zero_momentum_boundary(domain)

# Define tsunami wave (in metres and seconds).
the_wave = lambda t: [(20*np.sin(t*np.pi/(60*10)))*np.exp(-t/600), 0, 0]
Bw = anuga.Time_boundary(domain=domain, function=the_wave)

domain.set_boundary({'land_sse': Bs,
                     'land_s': Bs,
                     'bottom': Bs,
                     'ocean_wsw': Bw,
                     'ocean_w': Bw,
                     'ocean_wnw': Bw,
                     'top': Bs,
                     'land_nne': Bs,
                     'land_ese': Bs,
                     'land_se': Bs})


#------------------------------------------------------------------------------
# Evolve system through time
#------------------------------------------------------------------------------

evolveStartTime = time.time()


# Save every two mins leading up to wave approaching land
for t in domain.evolve(yieldstep=2*60,
                       finaltime=5000):
    print domain.timestepping_statistics()
    print domain.boundary_statistics(tags='ocean_wnw')

# Save every 30 secs as wave starts inundating ashore
for t in domain.evolve(yieldstep=60*0.5,
                       finaltime=7000,
                       skip_initial_step=True):
    print domain.timestepping_statistics()
    print domain.boundary_statistics(tags='ocean_wnw')




#------------------------------------------------------------------------------
# Upload Result Files to Cloud Storage
#------------------------------------------------------------------------------
def cloudUpload(inFilePath, cloudKey):
    cloudBucket = os.environ["STORAGE_BUCKET"]
    cloudDir = os.environ["STORAGE_BASE_KEY_PATH"]
    queryPath = (cloudBucket + "/" + cloudDir + "/" + cloudKey).replace("//", "/")
    retcode = subprocess.call(["cloud", "upload", cloudKey, inFilePath, "--set-acl=public-read"])
    print ("cloudUpload: " + inFilePath + " to " + queryPath + " returned " + str(retcode))


uploadStartTime = time.time()

# Upload results
print 'Uploading result files'
cloudUpload("${input_dataset}", "raw_elevation")
cloudUpload("${name_stem}_UTM.nc", "${name_stem}_UTM.nc")
cloudUpload("${name_stem}.asc", "${name_stem}.asc")
cloudUpload("${name_stem}.prj", "${name_stem}.prj")
cloudUpload("${name_stem}.dem", "${name_stem}.dem")
cloudUpload("${name_stem}.pts", "${name_stem}.pts")
cloudUpload("${name_stem}.msh", "${name_stem}.msh")
cloudUpload("${name_stem}_fixed_wave.sww", "${name_stem}_fixed_wave.sww")

print 'If you wish to view your output - please look at anuga-viewer here: http://sourceforge.net/projects/anuga/files/'

print '''
---------------
| Timer Stats |
---------------
'''
print 'Convert/Fit   : %.2f seconds' %(bounaryStartTime-jobstart)
print 'Bounding      : %.2f seconds' %(evolveStartTime-bounaryStartTime)
print 'Evolve        : %.2f seconds' %(uploadStartTime-evolveStartTime)
print 'Upload        : %.2f seconds' %(time.time()-uploadStartTime)
print 'Total time: %.2f seconds' %(time.time()-jobstart)
