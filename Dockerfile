FROM python:3.10-slim

# Install transitive dependencies
RUN apt-get update \
 && apt-get install -y git libspatialindex-dev libgdal-dev libproj-dev

# Add source
WORKDIR /app
ADD . .

# Install pdgraster from source
RUN pip install .

CMD ["python"]
