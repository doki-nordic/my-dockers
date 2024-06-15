FROM ubuntu:20.04

# Packages to install
ARG ARG_LINUX_PACKAGES="sudo udev usbutils wget curl python3 mc"

# Install linux packages (with cache)
RUN rm -f /etc/apt/apt.conf.d/docker-clean; echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
	--mount=type=cache,target=/var/lib/apt,sharing=locked \
	apt update && \
	DEBIAN_FRONTEND=noninteractive apt install -y -qq $ARG_LINUX_PACKAGES

# The my-dockers scripts will provide user information allowing
# to user your user name from host.
ARG UN
ARG UI
ARG GN
ARG GI

# Setup user account
RUN groupadd -g $GI $GN && \
	useradd -s `which bash` -m -g $GI -G adm,dialout,cdrom,sudo,dip,plugdev -u $UI $UN && \
	echo "$UN ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/$UN

USER $UN:$GN

WORKDIR /home/$UN
