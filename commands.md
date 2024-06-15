
Outdated state:
 * Up to date
 * Outdated
 * building image disposes the container, so there will be no other states

`command ...`
 * build image automatically if empty
 * warn about changes in dockerfile

`command -q ...`
 * Skip interactive prompts
 * don't warn

`command [command]`
 * execute command in container
 * `bash` by default
 * start or unpause if needed
```
--> command_name
image_name = IMAGE_FROM_COMMAND(command_name)
if image_outdated:
    warning that is outdated
```

`command -build`
 * build associated image
 * if containers (this or others) exists, ask to dispose
   ```
   The following commands are using previous version of the image:
    - ncs
    - zephyr
   Do you want to dispose them all [Y/n]?
   ```
```
--> command_name
if container exists:
    ask if user is sure
    stop and remove container
image_name = IMAGE_FROM_COMMAND(command_name)
BUILD_IMAGE(image_name)
PURGE_IMAGES()
```

`command -stop`
 * stop container, but don't dispose state
 * there is no `-start` option, because the container will start
   on the first usage.
```
--> command_name
STOP_CONTAINER(command_name)
```

`command -dispose`
 * ask if user is sure
 * remove container
```
--> command_name
REMOVE_CONTAINER(command_name)
```

`command -dispose-image`
 * ask if user is sure
 * remove container
 * remove image

`my-dockers`
 * show status of everything
 * create commands in `bin` directory
 * if some findings, ask if user wants to fix them (update images and containers)


