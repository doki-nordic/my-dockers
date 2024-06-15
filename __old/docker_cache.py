
import docker
import docker.models.images

client = docker.from_env()

_list_images = None

def list_images() -> 'list[docker.models.images.Image]':
    if _list_images is None:
        _list_images = list(client.images.list())
    return _list_images

