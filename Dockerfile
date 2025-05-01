FROM condaforge/mambaforge:24.3.0-0

LABEL maintainer="jvillada@lbl.gov"
LABEL version="v0.1"
LABEL software="symclatron: symbiont classifier"

ADD symclatron /usr/src/symclatron/
ADD data /usr/src/symclatron/data
ADD requirements.txt /usr/src/symclatron/requirements.txt

RUN mamba install -c bioconda --file /usr/src/symclatron/requirements.txt -y
RUN mamba clean --all

ENV PATH=${PATH}:/usr/src/symclatron
WORKDIR /usr/src/symclatron/