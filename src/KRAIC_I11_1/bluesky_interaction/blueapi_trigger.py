from blueapi.client.client import BlueapiClient
from blueapi.service.model import TaskRequest

blueapi_client = BlueapiClient.from_config_file("./i11-1.yaml")

task = TaskRequest(name="trigger_detector", params={}, instrument_session="cm12345-1")

task_status = blueapi_client.run_task(task)


if task_status.task_failed:
    raise RuntimeError()
