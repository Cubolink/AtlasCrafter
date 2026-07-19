import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from renders.models import RenderJob
from renders.services import claim_next_queued_job, execute_render_job


class Command(BaseCommand):
    help = "Process queued BlueMap render jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process currently available jobs and exit.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=settings.BLUEMAP_RENDER_WORKER_CONCURRENCY,
            help="Maximum number of render jobs this worker may run in parallel.",
        )
        parser.add_argument(
            "--poll-seconds",
            type=int,
            default=settings.BLUEMAP_RENDER_WORKER_POLL_SECONDS,
            help="Seconds to wait before polling for queued jobs again.",
        )

    def handle(self, *args, **options):
        concurrency = max(1, options["concurrency"])
        poll_seconds = max(1, options["poll_seconds"])
        once = options["once"]
        futures = set()

        self.stdout.write(
            self.style.SUCCESS(
                f"Render worker started with concurrency={concurrency}"
            )
        )

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            while True:
                close_old_connections()

                while len(futures) < concurrency:
                    job = claim_next_queued_job(max_running=concurrency)
                    if job is None:
                        break
                    self.stdout.write(f"Claimed render job #{job.id}")
                    futures.add(executor.submit(run_claimed_job, job.id))

                if once and not futures:
                    if not RenderJob.objects.filter(status=RenderJob.Status.QUEUED).exists():
                        break

                if futures:
                    done, futures = wait(
                        futures,
                        timeout=poll_seconds,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in done:
                        job_id = future.result()
                        self.stdout.write(f"Finished render job #{job_id}")
                elif once:
                    break
                else:
                    time.sleep(poll_seconds)


def run_claimed_job(job_id: int) -> int:
    close_old_connections()
    try:
        job = RenderJob.objects.select_related(
            "render__atlas__project",
            "render__atlas__world_folder__default_resource_source",
            "render__atlas__world_folder__minecraft_server__resource_source",
            "render__resource_source",
            "requested_by",
        ).get(id=job_id)
        execute_render_job(job)
        return job_id
    finally:
        close_old_connections()
