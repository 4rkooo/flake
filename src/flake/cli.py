import subprocess

import typer
from rich import print
from rich.table import Table

from . import memory
from .harness import canary, retro, versions
from .world import simulator

app = typer.Typer()
GROUP = "taco-council"


@app.command()
def seed() -> None:
    subprocess.run(["python", "scripts/seed.py"], check=True)


@app.command()
def plan(brief: str) -> None:
    from .agent.graph import run_plan  # imported here so `flake seed` works without LLM keys

    ep = run_plan(GROUP, brief)
    print(f"[bold]{ep['_id']}[/] booked under {ep['version_id']}: {ep.get('booking')}")


@app.command()
def tick(days: int = typer.Argument(7)) -> None:  # Argument so `flake tick 7` works; a plain default would be --days
    for plan_id in simulator.tick(days):
        ep = memory.get_episode(plan_id)
        print(f"{plan_id}: {ep['outcomes']}")
        result = canary.evaluate(GROUP, ep)
        if result:
            print(f"[bold]canary {ep['version_id']}: {result}[/]")


@app.command("retro")
def retro_cmd(reckless: bool = False) -> None:
    out = retro.run(GROUP, retro.RECKLESS if reckless else None)

    t = Table("friend", "n", "bails", "P(flake)", "upper 90%", "pays late", "Flake Score")
    for p, prof in out["profiles"].items():
        f, l = prof["flake"], prof["pay_late"]
        t.add_row(p, str(f["n"]), str(f["k"]), f"{f['p_mean']:.2f}", f"{f['p_upper90']:.2f}", f"{l['p_mean']:.2f}", str(prof["flake_score"]))
    print(t)
    bt = out["backtest"]
    # the delta replays every resolved plan, so it grows as live plans resolve: narrate this line, not a memorized number
    colour = "green" if bt["delta_usd"] >= 0 else "red"
    print(f"backtest over {bt['episodes']} past plans: current policy ${bt['baseline_usd']:.2f}, "
          f"proposed ${bt['proposed_usd']:.2f} -> [bold {colour}]{bt['delta_usd']:+.2f}[/]")
    print(f"[bold]{out['version_id']} -> {out['status']}[/]")


@app.command("versions")
def versions_cmd() -> None:
    t = Table("version", "status", "rules", "exposure cap", "auto spend", "backtest")
    for v in versions.history(GROUP):
        p = v["policy"]
        t.add_row(
            v["_id"],
            v["status"],
            str(len(p["rules"])),
            str(p["guardrails"]["max_nonrefundable_exposure_usd"]),
            str(p["guardrails"]["max_auto_spend_usd"]),
            str((v.get("backtest") or {}).get("delta_usd", "-")),
        )
    print(t)


@app.command()
def diff(a: str, b: str) -> None:
    for line in versions.diff(f"{GROUP}:{a}", f"{GROUP}:{b}"):
        print(line)


@app.command()
def rollback() -> None:
    print(f"active is now {versions.rollback(GROUP)}")


@app.command()
def audit(plan_id: str) -> None:
    from .config import db

    for d in db.audit_log.find({"episode_id": plan_id}).sort("ts", 1):
        print(f"{d['tool']}: {d['decision']} ({d['reason']})")


if __name__ == "__main__":
    app()
