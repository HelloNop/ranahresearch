"""Run the discovery API journey against a running API and worker."""

import argparse
import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--idea",
        default="Pengaruh generative AI terhadap hasil belajar mahasiswa di pendidikan tinggi.",
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    token = os.environ["RANAH_LOCAL_TOKEN"]

    def request(path: str, data: dict[str, Any] | None = None) -> Any:
        req = Request(
            args.url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise SystemExit(exc.read().decode()) from exc

    project = request("/projects", {"idea": args.idea})
    base = f"/projects/{project['id']}"

    def run(path: str) -> None:
        operation = request(base + path, {})
        deadline = time.monotonic() + 1800
        previous = ""
        while operation["status"] in ("PENDING", "RUNNING"):
            if time.monotonic() > deadline:
                raise SystemExit(f"Operation remains active: {operation['operation_id']}")
            operation = request(base + f"/operations/{operation['operation_id']}")
            if operation["stage"] != previous:
                print(operation["stage"])
                previous = operation["stage"]
            time.sleep(1)
        if operation["status"] == "FAILED":
            raise SystemExit(operation)
        if operation["status"] == "PARTIAL":
            print("Partial discovery:", operation["provider_runs"])

    print("Created project:", project["id"])
    run("/plan/generate")
    plan = request(base + "/plan")
    print(json.dumps(plan["content"], ensure_ascii=False, indent=2))
    print(json.dumps(request(base + "/framework"), ensure_ascii=False, indent=2))
    if input("Approve this proposed plan? [yes/no] ").strip().lower() != "yes":
        print("Plan remains proposed; project is saved.")
        return
    request(base + "/plan/approve", {"plan_id": plan["id"]})
    run("/search-strategy/generate")
    print(json.dumps(request(base + "/search-strategy"), ensure_ascii=False, indent=2))
    run("/literature/search")
    for work in request(base + "/literature"):
        print(work["publication_year"], work["title"], work["doi"], work["verification_status"])
    print("Discovery finished. Records have not been screened.")


if __name__ == "__main__":
    main()
