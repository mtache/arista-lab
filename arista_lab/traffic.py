from pathlib import Path
import pickle
import snappi # type: ignore[import-untyped]
import snappi_ixnetwork # type: ignore[import-untyped]
import logging
from rich.table import Table
from rich.console import Console
import urllib3

urllib3.disable_warnings()
console = Console()
logger = logging.getLogger(__name__)

snappi_ixnetwork_session_file = Path("./.snappi-api-session")

def configure(
    api: snappi.Api,
    config: snappi.Config,
) -> None:
    """Configure the flows on the traffic generator"""
    try:
        api.set_config(config)
    except Exception as e:
        logger.error(e) # snappi_ixnetwork.exceptions.IxNetworkException is raised here
    if isinstance(api, snappi_ixnetwork.Api):
        with snappi_ixnetwork_session_file.open(mode="wb") as fd:
            pickle.dump(api.get_config(), fd)

def _get_traffic_stats(api: snappi.Api) -> tuple[list, list]:
    request = api.metrics_request()
    request.choice = request.PORT
    port_stats = api.get_metrics(request).port_metrics
    if port_stats is None:
        port_stats = []

    request = api.metrics_request()
    request.choice = request.FLOW
    flow_stats = api.get_metrics(request).flow_metrics
    if flow_stats is None:
        flow_stats = []
    return port_stats, flow_stats

def _print_traffic_stats(
    port_stats=None,
    flow_stats=None,
    bgpv4_stats=None,
    bgpv6_stats=None,
) -> None:
    if port_stats is not None:
        table = Table(title="Port Metrics")
        table.add_column("Port")
        table.add_column("Tx Frames")
        table.add_column("Tx Bytes")
        table.add_column("Rx Frames")
        table.add_column("Rx Bytes")
        table.add_column("Tx FPS")
        table.add_column("Rx FPS")
        for stat in port_stats:
            table.add_row(
                stat.name,
                str(stat.frames_tx),
                str(stat.bytes_tx),
                str(stat.frames_rx),
                str(stat.bytes_rx),
                str(stat.frames_tx_rate),
                str(stat.frames_rx_rate),
            )
        console.print(table)
    if flow_stats is not None:
        table = Table(title="Flow Metrics")
        table.add_column("Flow")
        table.add_column("Rx Frames")
        table.add_column("Rx Bytes")
        table.add_column("Transmit State")
        for stat in flow_stats:
            table.add_row(
                stat.name,
                str(stat.frames_rx),
                str(stat.bytes_rx),
                stat.transmit,
            )
        console.print(table)
    if bgpv4_stats is not None:
        table = Table(title="BGPv4 Metrics")
        table.add_column("Name")
        table.add_column("Session State")
        table.add_column("Session Flaps")
        table.add_column("Routes Advertised")
        table.add_column("Routes Received")
        table.add_column("Route Withdraws Tx")
        table.add_column("Route Withdraws Rx")
        table.add_column("Keepalives Tx")
        table.add_column("Keepalives Rx")
        for stat in bgpv4_stats:
            table.add_row(
                stat.name,
                stat.session_state,
                str(stat.session_flap_count),
                str(stat.routes_advertised),
                str(stat.routes_received),
                str(stat.route_withdraws_sent),
                str(stat.route_withdraws_received),
                str(stat.keepalives_sent),
                str(stat.keepalives_received),
            )
        console.print(table)
    if bgpv6_stats is not None:
        table = Table(title="BGPv6 Metrics")
        table.add_column("Name")
        table.add_column("Session State")
        table.add_column("Session Flaps")
        table.add_column("Routes Advertised")
        table.add_column("Routes Received")
        table.add_column("Route Withdraws Tx")
        table.add_column("Route Withdraws Rx")
        table.add_column("Keepalives Tx")
        table.add_column("Keepalives Rx")
        for stat in bgpv6_stats:
            table.add_row(
                stat.name,
                stat.session_state,
                str(stat.session_flap_count),
                str(stat.routes_advertised),
                str(stat.routes_received),
                str(stat.route_withdraws_sent),
                str(stat.route_withdraws_received),
                str(stat.keepalives_sent),
                str(stat.keepalives_received),
            )
        console.print(table)

def start(api: snappi.Api) -> None:
    """Start the flows on the traffic generator"""
    control_state = api.control_state()
    control_state.choice = control_state.TRAFFIC
    control_state.traffic.choice = control_state.traffic.FLOW_TRANSMIT
    control_state.traffic.flow_transmit.state = control_state.traffic.flow_transmit.START
    try:
        res = api.set_control_state(control_state)
        for warning in res.warnings:
            logger.warning(warning)
    except Exception as e:
        logger.error(e)

def stop(api: snappi.Api) -> None:
    """Stop the flows on the traffic generator"""
    control_state = api.control_state()
    control_state.choice = control_state.TRAFFIC
    control_state.traffic.choice = control_state.traffic.FLOW_TRANSMIT
    control_state.traffic.flow_transmit.state = (
        control_state.traffic.flow_transmit.STOP
    )
    try:
        res = api.set_control_state(control_state)
        for warning in res.warnings:
            logger.warning(warning)
    except Exception as e:
        logger.error(e)

def stats(api: snappi.Api) -> None:
    port_stats, flow_stats = _get_traffic_stats(api)
    _print_traffic_stats(port_stats=port_stats, flow_stats=flow_stats)
