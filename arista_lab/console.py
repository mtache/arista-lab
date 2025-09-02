from rich.progress import Progress
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import AggregatedResult


def _print_failed_tasks(bar: Progress, results: AggregatedResult) -> None:
    for host, multi_results in results.items():
        for r in multi_results:
            if r.failed:
                if isinstance(r.exception, NornirSubTaskError):
                    # Do not display NornirSubTaskError
                    continue
                if r.exception is not None:
                    bar.console.log(
                        f"Task {multi_results.name}/{r.name} failed for device {host}: {r.exception.__class__.__name__}"
                    )
                    bar.console.log(r.exception)
                elif r.result is not None:
                    bar.console.log(
                        f"Task {multi_results.name}/{r.name} failed for device {host}: {r.result}"
                    )
                else:
                    bar.console.log(
                        f"Task {multi_results.name}/{r.name} failed for device {host}"
                    )