import datetime
import json
import logging
import os
import re
import sys

from flywheel import Flywheel

import measurement_from_label

# Add logging...
logging.basicConfig()
log = logging.getLogger('pfile-classifier')


### Function definitions
def get_fw_sessions(fw, container_type, container_id):
    """
    Get project sessions based off of container type (project or session)
    """
    if container_type == 'project':
        log.info('Getting sessions within project')
        # Get project
        project = fw.get_project(container_id)
        # Get list of sessions within project
        project_sessions = fw.get_project_sessions(container_id)
        project_id = container_id
    elif container_type == 'session':
        log.info('Getting session')
        # If container ID is actually a session, get the specific session
        session = fw.get_session(container_id)
        # Place the single session within a list to iterate over (mirrors project_sessions above)
        project_sessions = [session]
        project_id = session['project']
    else:
        # TODO: test that this works!!
        log.error("Container ID %s is not associated with a project or a session" % container_id)
        sys.exit(1)

    return project_sessions, project_id


def find_efile_pfile(acq, files_found):
    """
    Determine if a pfile exists in acquisition
    """
    # Initialize booleans
    pfile_found = False
    efile_found = False
    # Iterate over files
    for f in acq['files']:
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
                    'files': acq['files'],
                    'efile_name': efilename,
                    'pfile_name': pfilename,
                    'timestamp': acq.get('timestamp')
                    }

def convert_string(value):
    """

    Try to convert value to an integer or float.

    If unable to convert without raising a Value Error,
        leave value as type string.

    """
    try:
        value = int(value)
    except ValueError:
        try:
            value = float(value)
        except ValueError:
            pass

    return value

def convert_to_si(value):
    """ Convert the value to into SI units

    msec are converted to seconds
    mm are converted to meters
    degrees remain within degrees (only 'deg.' label is removed)

    """
    # Define
    conversions = {
            'msec': 1000,
            'mm': 1000,
            'deg.': 1,
            }
    # Split number and label up
    num, label = value.split(' ')
    # Convert string to a number (int or float)
    num = convert_string(num)

    return num * conversions[label]

def parse_efile(path):
    """
    Parse efile contents.
    Returns dictionary of key/value pairs parsed from the efile.
    """
    log.debug('Parsing efile')
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

        # Handle values with the following labels
        if re.match("[0-9]*[.]?[0-9]* (mm|deg|msec)", value):
            # Convert to SI unit...
            value = convert_to_si(value)
        # Otherwise, try to convert value to int, float or leave as string
        else:
            value = convert_string(value)


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

    ## Handle date/time
    # date_of_scan --- in format  MM/DD/YYY - GE date format
    # time_of_scan --- in format HH/MM  -- only hours/minutes
    date_of_scan = info['date_of_scan']
    time_of_scan = info['time_of_scan']
    # Assert if matches the expected format
    if re.match("\d{2}/\d{2}/\d{3}", date_of_scan) and re.match("\d{2}:\d{2}", time_of_scan):
        MM,DD,YYY = date_of_scan.split('/')
        HH, mm = time_of_scan.split(':')
        # Create date time object
        date_time_of_scan = datetime.datetime(int(YYY) + 1900, int(MM), int(DD), int(HH), int(mm))
        # Remove values from dictionary
        info.pop('date_of_scan')
        info.pop('time_of_scan')

    return date_time_of_scan, info


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

    ### Get session(s) ###
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
            find_efile_pfile(acq, files_found)

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
        date_time_of_scan, info = parse_efile(path)

        ## Check if acquisition timestamp is assign, if not, use date_time_of_scan
        if files_found[acq_id]['timestamp'] is None:
            # TODO: Understand how to handle timezone
            #fw.modify_acquisition(acq_id, {'timestamp': date_time_of_scan.strftime('%Y-%m-%dT%H:%M:%SZ%z')})
            pass

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
            # Check if pfilename is in filename and is not 'physio'
            if pfile_name_noextension in f['name'] and ('physio' not in f['name']):
                # Add the classification to the file
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
