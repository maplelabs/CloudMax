import datetime
import json
import logging
import math
import random
import re
import time
from typing import List
from chaosk8s import create_k8s_api_client  # ✅ Add this import
 
from chaoslib.exceptions import ActivityFailed
from chaoslib.types import Secrets
from kubernetes import client, config, stream
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.stream.ws_client import ERROR_CHANNEL, STDERR_CHANNEL, STDOUT_CHANNEL
 
__all__ = [
    "create_node",
    "delete_nodes",
    "cordon_node",
    "drain_nodes",
    "uncordon_node",
]
logger = logging.getLogger("chaostoolkit")
 
 
def _select_nodes(
    name: str = None,
    label_selector: str = None,
    count: int = None,
    secrets: Secrets = None,
    pod_label_selector: str = None,
    pod_namespace: str = None,
    first: bool = False,
) -> List[client.V1Node]:
    """
    Selects nodes of the kubernetes cluster based on the input parameters and
     returns them.
    If no input parameter is given, all nodes are returned.
    In case that no node can be found or matches the filter paramter an
     exception is thrown.
 
    Nodes can be filtered by their name through the `name` paramteter.
    Nodes can be filtered by their label through the `label_selector`
    parameter.
    Nodes can further be filtered by the pods that they are accommodating using
    the pod's label through the `pod_label_selector` parameter and
    `pod_namespace` parameter.
    The amount of nodes to return can be capped through the `count` paramteter.
    In this case `count` random nodes will be returned.
    If first is set to true only the first node is returned.
    """
    nodes = []
    # api = create_k8s_api_client(secrets)
    api = None
    try:
        config.load_incluster_config()
        api = client.ApiClient()
        print("🔑 [DEBUG] Kubernetes API client created in _select_nodes")
    except Exception as e:
        print(f"❌ [DEBUG] Failed to create k8s api client in _select_nodes: {e}")
        raise
   
    v1 = client.CoreV1Api(api)
 
    if name and not label_selector:
        logger.debug(f"Filtering nodes by name {name}")
        ret = v1.list_node(field_selector=f"metadata.name={name}")
        logger.debug(f"Found {len(ret.items)} nodes")
    elif label_selector and not name:
        logger.debug(f"Filtering nodes by label {label_selector}")
        ret = v1.list_node(label_selector=label_selector)
        logger.debug(f"Found {len(ret.items)} nodes")
    elif name and label_selector:
        logger.debug(
            "Filtering nodes by name %s and \
                      label %s"
            % (name, label_selector)
        )
        ret = v1.list_node(
            field_selector=f"metadata.name={name}",
            label_selector=label_selector,
        )
        logger.debug(f"Found {len(ret.items)} nodes")
    else:
        ret = v1.list_node()
 
    if pod_label_selector and pod_namespace:
        logger.debug(f"Filtering nodes by pod label {pod_label_selector}")
        pods = v1.list_namespaced_pod(
            pod_namespace, label_selector=pod_label_selector
        )
        for node in ret.items:
            for pod in pods.items:
                if pod.spec.node_name == node.metadata.name:
                    nodes.append(node)
                    pass
        logger.debug(f"Found {len(nodes)} nodes")
    else:
        nodes = ret.items
 
    if not nodes:
        raise ActivityFailed("failed to find a node that matches selector")
 
    if first:
        nodes = [nodes[0]]
    elif count is not None:
        nodes = random.choices(nodes, k=count)
    logger.debug(
        f"Picked nodes '{', '.join([n.metadata.name for n in nodes])}'"
    )
 
    return nodes
 
 
 
def cordon_node(
    name: str = None, label_selector: str = None, secrets: Secrets = None
) -> List[str]:
    """
    Cordon nodes matching the given label or name, so that no pods
    are scheduled on them any longer.
    """
    # api = create_k8s_api_client(secrets)
    api = None
    try:
        config.load_incluster_config()
        api = client.ApiClient()
        print("🔑 [DEBUG] Kubernetes API client created")
    except Exception as e:
        print(f"❌ [DEBUG] Failed to create k8s api client: {e}")
        raise
 
    v1 = client.CoreV1Api(api)
 
    nodes = _select_nodes(
        name=name, label_selector=label_selector, secrets=secrets
    )
 
    body = {"spec": {"unschedulable": True}}
 
    cordoned = []
    for n in nodes:
        try:
            v1.patch_node(n.metadata.name, body)
            cordoned.append(n.metadata.name)
        except ApiException as x:
            logger.debug(
                f"Unscheduling node '{n.metadata.name}' failed: {x.body}"
            )
            raise ActivityFailed(
                f"Failed to unschedule node '{n.metadata.name}': {x.body}"
            )
 
    return cordoned
 
 
def uncordon_node(
    name: str = None, label_selector: str = None, secrets: Secrets = None
) -> List[str]:
    """
    Uncordon nodes matching the given label name, so that pods can be
    scheduled on them again.
    """
    # api = create_k8s_api_client(secrets)
    api = None
    try:
        config.load_incluster_config()
        api = client.ApiClient()
        print("🔑 [DEBUG] Kubernetes API client created")
    except Exception as e:
        print(f"❌ [DEBUG] Failed to create k8s api client: {e}")
        raise
 
    v1 = client.CoreV1Api(api)
 
    nodes = _select_nodes(
        name=name, label_selector=label_selector, secrets=secrets
    )
 
    body = {"spec": {"unschedulable": False}}
 
    uncordoned = []
    for n in nodes:
        try:
            v1.patch_node(n.metadata.name, body)
            uncordoned.append(n.metadata.name)
        except ApiException as x:
            logger.debug(
                f"Scheduling node '{n.metadata.name}' failed: {x.body}"
            )
            raise ActivityFailed(
                f"Failed to schedule node '{n.metadata.name}': {x.body}"
            )
 
    return uncordoned
