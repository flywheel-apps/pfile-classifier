# flywheel/pfile-classifier
#
# Use pyDicom to classify GE pfile. # TODO: possible improve this wording
#
# Example usage:
#  docker run --rm -ti \
#       -v /path/to/config.json:/flywheel/v0/config.json \
#	flywheel/pfile-classifier


FROM python:2.7
MAINTAINER Flywheel <support@flywheel.io>

# Install scitran.data dependencies
#RUN pip install \
#    pytz \
#    pydicom

# Install python SDK
RUN pip install https://github.com/flywheel-io/sdk/releases/download/0.2.0/flywheel-0.2.0-py2-none-linux_x86_64.whl

# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
RUN mkdir -p ${FLYWHEEL}
COPY run ${FLYWHEEL}/run
COPY manifest.json ${FLYWHEEL}/manifest.json

# Get latest measurement code
ADD https://raw.githubusercontent.com/scitran/utilities/master/measurement_from_label.py ${FLYWHEEL}/measurement_from_label.py

# Copy classifier code into place
COPY classify_pfile.py ${FLYWHEEL}/classify_pfile.py

# Set the entrypoint
ENTRYPOINT ["/flywheel/v0/run"]
