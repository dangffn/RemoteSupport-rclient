#!/bin/bash -e

# determine the architecture from the system
arch=$(dpkg-architecture --query=DEB_HOST_ARCH)
version=1.0.1
outputdir=./

while [[ $# -gt 0 ]]; do
	case "$1" in
		-a|--arch)
			# override architecture
			arch=$2
			shift
			shift
			;;
		-v|--version)
			# set the version
			version=$2
			shift
			shift
			;;
		-o|--output)
			# set the output file directory
			outputdir=$(echo $2 | sed 's:/\?$:/:g')
			shift
			shift
			;;
	esac
done

# update arch
sed -i "s/Architecture: .*$/Architecture: $arch/g" deb/DEBIAN/control
# update version
sed -i "s/Version: .*/Version: $version/g" deb/DEBIAN/control
# output package
deb_file="$outputdir"remotesupport_$version\_$arch.deb
deb_file_latest="$outputdir"remotesupport_latest_$arch.deb

# build the python binary
echo Building executable
echo Installing dependencies
pip3 install -r ./app/requirements.txt
python3 -m PyInstaller ./app/rclient.py \
	--onefile \
	--paths='./app/' \
	--paths='./app/modules' \
	--distpath='./app/dist' \
	--workpath='./app/build'

mv ./app/dist/rclient ./deb/usr/bin/

# build the debian package
echo Building $deb_file
dpkg-deb --build --root-owner-group deb "$deb_file"

# copy to latest file
cp "$deb_file" "$deb_file_latest"
