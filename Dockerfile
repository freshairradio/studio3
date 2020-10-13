
# modified from https://github.com/Gorialis/discord.py-docker/blob/master/dockerfiles/0_minimal/alpine.Dockerfile

FROM python:3.7-alpine

RUN \
    # basic deps
    apk --no-cache add cloc openssl openssl-dev openssh alpine-sdk bash gettext build-base gnupg linux-headers xz \
    # voice support
    libffi-dev libsodium-dev opus-dev ffmpeg 

RUN pip install pipenv 

WORKDIR /opt/bot

ADD Pipfile.lock .
ADD Pipfile .

RUN pipenv install --system --deploy --ignore-pipfile

ADD bot2.py .

ENTRYPOINT [ "python3", "-u", "bot2.py" ]