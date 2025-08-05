# Use the pixi base image
FROM ghcr.io/prefix-dev/pixi:0.46.0

LABEL maintainer="jvillada@lbl.gov"
LABEL version="0.3.1"
LABEL software="symclatron: symbiont classifier"

# Create and set working directory
WORKDIR /usr/src/symclatron

# Add required files
COPY pixi.toml ./
COPY symclatron ./

# Make sure the symclatron script is executable
RUN chmod +x ./symclatron

# Install dependencies and set up data
RUN pixi install && \
    pixi run -- ./symclatron setup

# Add the symclatron to PATH
ENV PATH="${PATH}:/usr/src/symclatron"

# Create a wrapper script that ensures we're in the correct directory
RUN echo '#!/bin/bash\ncd /usr/src/symclatron\nexec "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Set the entrypoint to our wrapper script
ENTRYPOINT ["/entrypoint.sh"]

# Set default command to show help
CMD ["pixi", "run", "--", "./symclatron", "--help"]