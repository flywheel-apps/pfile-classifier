CONTAINER=flywheel/pfile-classifier
DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

docker build --tag $CONTAINER $DIR
