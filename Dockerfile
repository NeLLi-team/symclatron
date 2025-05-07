FROM ghcr.io/prefix-dev/pixi:0.46.0

LABEL maintainer="jvillada@lbl.gov"
LABEL version="v0.1"
LABEL software="symclatron: symbiont classifier"

ADD pixi.toml /usr/src/symclatron/pixi.toml
ADD symclatron /usr/src/symclatron/
ADD data.tar.gz /usr/src/symclatron/data.tar.gz

WORKDIR /usr/src/symclatron/
RUN pixi install
RUN pixi run setup

ENV PATH=${PATH}:/usr/src/symclatron
WORKDIR /usr/src/symclatron/