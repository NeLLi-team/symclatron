FROM mambaorg/micromamba:1.5.10

ARG SYMCLATRON_VERSION=0.7.2
ARG MAMBA_DOCKERFILE_ACTIVATE=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER root
ENV MAMBA_ROOT_PREFIX=/opt/conda

RUN micromamba install -y -n base -c conda-forge -c bioconda -c https://repo.prefix.dev/astrogenomics \
        "symclatron=${SYMCLATRON_VERSION}" hmmer \
    && micromamba clean -a -y \
    && micromamba run -n base symclatron setup

WORKDIR /work
RUN chown -R mambauser:mambauser /work
USER mambauser

ENTRYPOINT ["micromamba", "run", "-n", "base", "symclatron"]
CMD ["--help"]
