import datetime
import json
import logging
import os
from pprint import pprint
import re
import sys

from flywheel import Flywheel

import measurement_from_label

# TODO: Add logging...
logging.basicConfig()
log = logging.getLogger('pfile-classifier')


### Function definitions
def get_fw_sessions(fw, container_type, container_id):
    """
    Get project sessions based off of container type (project or session)
    """
    log.debug('get_fw_session')
    if container_type == 'project':
        # Get project
        project = fw.get_project(container_id)
        # Get list of sessions within project
        project_sessions = fw.get_project_sessions(container_id)
        project_id = container_id
    elif container_type == 'session':
        # If container ID is actually a session, get the specific session
        session = fw.get_session(container_id)
        # Place the single session within a list to iterate over (mirrors project_sessions above)
        project_sessions = [session]
        project_id = session['project']
    else:
        # TODO: test that this works!!
        log.error("Container ID %s is not associated with a project or a session" % container_id)
        #raise Exception

    return project_sessions, project_id


def find_efile_pfile(files, files_found):
    """
    Determine if a pfile exists in acquisition
    """
    log.debug('find_efile_pfile')
    # Initialize booleans
    pfile_found = False
    efile_found = False
    # Iterate over files
    for f in files:
        # Check if file has a type
        if f.get('type'):
            # Determine if a pfile or efile without a classification is present
            # efile
            if ('pfile' in f['type']) and (f['name'][0] == 'E') and (not f.get('measurements')):
                efilename = f['name']
                efile_found = True
            # pfile
            elif ('pfile' in f['type']) and (not f.get('measurements')):
                pfilename = f['name']
                pfile_found = True
            else:
                continue
    # If both pfile and efile are within acquisition, we are going to classify the files...
    if pfile_found and efile_found:
        files_found[acq['_id']] = {
                    'files': files,
                    'efile_name': efilename,
                    'pfile_name': pfilename,
                    }


def parse_efile(path):
    """
    Parse efile contents.
    Returns dictionary of key/value pairs parsed from the efile.
    """
    log.debug('parse_efile')
    # Read in file
    fp = open(path, 'r')
    contents = fp.readlines()
    fp.close()
    # Iterate over every line in E-file
    info = dict()
    for idx in range(len(contents)):
        # Get meta information from single line with the E-file
        line = contents[idx]
        # Split into a key,value pair
        key, value = line.split('=')
        # Replace any spaces in key with an underscore
        value = value.strip()
        key = key.strip()
        key = key.replace(" ", "_")

        ### Special handling of values!
        #   i.e.
        #       values that contain labels such as "deg.", "mm", or "msec"
        #       any date in format MM/DD/YYY
        #       "gw_point" key

        # Handle values with labels
        # TODO!!! finish this
        if re.match("[0-9]*[.][0-9]* (mm|deg|msec)", value):
            print "Key: ", key, " Value: ", value
            print "Do something"
            # TODO: Convert to SI unit...
            # TODO: mm is not being picked up... float number?

        # Try to convert value to int, float, if ValueError raised on both, leave as string
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass

        ## Handle date
        # if value in format  MM/DD/YYY - convert to a date object
        if (type(value) is str) and re.match("\d{2}/\d{2}/\d{3}", value):
            MM,DD,YYY = value.split('/')
            value = datetime.date(int(YYY) + 1900, int(MM), int(DD))

        ## Slice information in E file
        # gw_point being nested, skip over...
        if 'gw_point' in key:
            continue
        # if key is a slice number, nest the following information
        if key == 'slice':
            info[line.strip()] = {
                "gw_point1": contents[idx+1].split('=')[-1].strip(),
                "gw_point2": contents[idx+2].split('=')[-1].strip(),
                "gw_point3": contents[idx+3].split('=')[-1].strip()
            }
        # regular case
        else:
            info[key] = value

    return info







if __name__ == '__main__':
    """
    """

    log.setLevel(getattr(logging, 'DEBUG'))

    ### Setup ###
    # Define base directory
    flywheel_basedir = '/flywheel/v0'
    # Get config file
    config_file = os.path.join(flywheel_basedir, 'config.json')
    if not os.path.exists(config_file):
        raise Exception('Config file (%s) does not exist' % config_file)
    with open(config_file, 'r') as fp:
        config_contents = json.load(fp)
    # Get api_key and container_id from gear config
    api_key = str(config_contents['inputs']['api_key']['key'])
    container_id = str(config_contents['destination']['id'])
    container_type = str(config_contents['destination']['type'])

    ### Get info using SDK ###
    # initiate fw class
    fw = Flywheel(api_key)
    # Get the sessions in the project and project ID
    project_sessions, project_id = get_fw_sessions(fw, container_type, container_id)

    ### Identify eligible efile/pfile pairs ###
    files_found = {}
    for session in project_sessions:
        session_id = session['_id']
        # Get all acquisitions within session
        session_acqs = fw.get_session_acquisitions(session_id)
        for acq in session_acqs:
            # Determine if efile and pfile are within acquisition
            find_efile_pfile(acq['files'], files_found)
    # Check if unclassified pfiles/efiles found
    if files_found:
        log.info("Identified %d acquisitions with an unclassified pfile and efile" % len(files_found))
    else:
        log.info("No unclassified efile/pfile pairings were identified within %s ID %s" % (container_type, container_id))
        log.info("Nothing to do...")
        sys.exit(0)


    ### Modify meta info ###
    # Define and create working dir
    working_dir = '/flywheel/v0/workdir'
    os.mkdir(working_dir)

    # Iterate over acquisitions
    for acq_id in files_found:
        # Get efilename and download
        efilename = files_found[acq_id]['efile_name']
        path = os.path.join(working_dir, efilename)
        fw.download_file_from_acquisition(acq_id, efilename, path)
        # Parse the efile
        info = parse_efile(path)
        pprint(info)


        ## Determine classification of pfile
        log.debug("Classifying pfile from series description")
        efile_measure = measurement_from_label.infer_measurement(info['series_description'])

        ## Modify files acquisition
        # 1) Add classification to all files with pfilename in filename (except physio)
        # 2) Add efile contents to file meta info on pfile (.7.gz), efile (E*.7), and nifti pfile (.7.nii.gz)

        ## (1) Add classification to all files with pfilename in filename (except physio)
        # Get pfilename without the .7.gz extension (P05120.7.gz -> P05120)
        pfile_name_noextension = files_found[acq_id]['pfile_name'].split('.')[0]
        # Iterate over every file within acquisition
        for f in files_found[acq_id]['files']:
            # Check if pfilename is in filename
            if pfile_name_noextension in f['name']:
                # check if physio data, if it is, move on...
                if 'physio' in f['name']:
                    continue
                # Otherwise, add the classification to the file
                else:
                    log.debug("Adding measurement %s to the file %s" % (efile_measure, f['name']))
                    #print "fw.set_acquisition_file_info(%s, %s, {'measurement': %s})" % (acq_id, f['name'], efile_measure)

        ## (2) Add efile contents to file meta info on pfile (.7.gz), efile (E*.7) and corresponding nifti pfile
        #fw.set_acquisition_file_info(acq_id, files_found[acq_id]['pfile_name'], info)
        print "fw.set_acquisition_file_info(%s, %s, info)" % (acq_id, files_found[acq_id]['pfile_name'])
        #fw.set_acquisition_file_info(acq_id, files_found[acq_id]['efile_name'], info)
        print "fw.set_acquisition_file_info(%s, %s, info)" % (acq_id, files_found[acq_id]['efile_name'])

        # TODO: add efile contents to file meta info on pfile in nifti format (.nii.gz) Determine if nifti file is present. Will this be delayed?
        #fw.set_acquisition_file_info(acq_id, files_found[acq_id]['pfile_nii_name'], info)
        #print "fw.set_acquisition_file_info(%s, %s, info)" % (acq_id, [''])

        #pprint(info)
