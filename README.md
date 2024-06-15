# my-dockers

Simplify creation and usage of personalized docker containers.

--------------------------------------------------------------

Those are scripts that I used to simplify my work using docker.
I polished them a little bit to make it more useable for others,
so take and enjoy if you like.

Requires **Python 3.8** or newer.
Tested on Ubuntu, with Ubuntu running in docker containers,
but it should also work on other Linux platforms.

## Installation

1. Clone or download the repository.
2. Run the `install.sh` script.
3. The installation script should create a `commands.yaml` file.
   You will put your configuration there in the next step.

## Configuration

1. Open `commands.yaml` file.
2. Add a command configuration there as described in the comments
   on the top of the file. Let's use this simple example:
   ```yaml
   docker-example:
     dockerfile: scripts/example.Dockerfile
   ```
3. Run `my-dockers` command. It will create command `docker-example`
   based on your configuration.

## Basic Usage

1. Run your new command in terminal. It will build the image,
   start docker container and run bash interactively in it.
   ```shell
   docker-example
   ```
2. Exit from container's bash.
   ```shell
   exit
   ```
3. Container is still running. You can go back to it at any time
   or run other commands in it.
   ```shell
   docker-example top
   ```
4. Running container in background will not take too much resources,
   but if you want to stop it, just type:
   ```shell
   docker-example -s   # or --stop
   ```

## Management of containers and images

1. At any time you can check the status of containers and images
   managed by the "my-dockers":
   ```shell
   my-dockers
   ```
2. If you don't need the container any more and you want to delate
   all the changes that you made there, type:
   ```shell
   docker-example -d   # or --delete
   ```
3. If you don't need the image any more, type:
   ```shell
   docker-example -del-img   # or --delete-image
   ```
4. Running the command will automatically build an image and start
   container if needed.
   ```shell
   docker-example
   ```
5. If you change anything in your source Dockerfile, the
   `my-dockers` script will detect that. Let's add `mc` linux
   package to the list of packages in the `example.Dockerfile`.
   Try how it works:
   ```shell
   my-dockers
   ```
   Try `mc` now.
   ```shell
   docker-example mc
   ```

## Directory sharing

1. Create some directory on your host system, for example:
   ```shell
   cd ~
   mkdir my-dockers-example
   ```
2. Add a that directory to share with docker container in
   the `commands.yaml` file. Replace `**your-user-name**` with
   your user name:
   ```yaml
   docker-example:
     dockerfile: scripts/example.Dockerfile
     share: /home/**your-user-name**/my-dockers-example
   ```
   **WARNING!!!** Don't share entire home directory or root
   directory. It my lead to disaster since container may
   override some important files on your host.

3. You have to delete current container since it is using older
   configuration.
   ```shell
   docker-example -d
   ```
4. Go to shared directory and start `docker-example` there.
   ```shell
   cd ~/my-dockers-example
   docker-example
   ```
   You may noticed that you are in the same directory
   as previously in the host.
5. Current directory is preserved if it is inside
   shared directory, for example:
   ```shell
   cd ~/my-dockers-example
   docker-example bash -c 'ps -aux > ./list.txt'
   cat list.txt
   ```
6. The `example.Dockerfile` creates a linux user with the same
   user name, user group, user id, and group id as in the host,
   so file owner is the same as in host:
   ```shell
   $ ls -l
   -rw-r--r-- 1 **your-user-name** **your-user-name** ...
   ```
