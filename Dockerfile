# Use the pixi base image
FROM ghcr.io/prefix-dev/pixi:0.46.0

LABEL maintainer="jvillada@lbl.gov"
LABEL version="v0.1"
LABEL software="symclatron: symbiont classifier"

# Create and set working directory
WORKDIR /usr/src/symclatron

# Add required files
COPY pixi.toml ./
COPY symclatron ./
COPY data.tar.gz ./

# Make sure the symclatron script is executable
RUN chmod +x ./symclatron

# Install dependencies and set up data
RUN pixi install && \
    ./symclatron setup

# Add the symclatron to PATH
ENV PATH="${PATH}:/usr/src/symclatron"

# Set default command to show help
CMD ["./symclatron", "--help"]