"""Gameplay panels for the 3D client: R&D Complex, Mission Control,
and the post-launch result panel shown during the launch sequence."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ursina import Button, Entity, Text, color

from baris.resolver import (
    effective_base_success,
    effective_launch_cost,
    effective_rocket,
    meets_architecture_prereqs,
    visible_missions,
)
from baris.state import (
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_FULL_NAMES,
    ARCHITECTURE_SUCCESS_DELTA,
    Architecture,
    LaunchReport,
    MIN_RELIABILITY_TO_LAUNCH,
    MISSIONS_BY_ID,
    MissionId,
    Module,
    ObjectiveId,
    ProgramTier,
    RELIABILITY_SWING_PER_POINT,
    Rocket,
    objectives_for,
    program_name,
    rocket_display_name,
)

from baris.client3d.panels_info import _close_button, _panel_shell, format_programs

if TYPE_CHECKING:
    from baris.client3d.app import BarisClient


# ----------------------------------------------------------------------
# R&D Complex
# ----------------------------------------------------------------------
def build_rd_panel(client: "BarisClient", parent: Entity) -> Entity:
    me = client.me()
    root, w, h = _panel_shell(parent, "R&D COMPLEX", title_color=(110, 200, 120))
    if me is None:
        _close_button(client, root, -0.37)
        return root

    Text(
        text=f"Budget: {me.budget} MB      Queued spend: {client.rd_spend} MB",
        parent=root, position=(0, 0.3),
        origin=(0, 0), scale=1.1, color=color.rgb32(220, 225, 235),
    )

    # Target buttons: Light / Medium / Heavy / Docking Module.
    targets: list[tuple[str, str, str]] = [
        (Rocket.LIGHT.value,  rocket_display_name(Rocket.LIGHT, me.side),  "Q"),
        (Rocket.MEDIUM.value, rocket_display_name(Rocket.MEDIUM, me.side), "W"),
        (Rocket.HEAVY.value,  rocket_display_name(Rocket.HEAVY, me.side),  "E"),
        (Module.DOCKING.value, "Docking Module",                           "R"),
    ]
    x_positions = [-0.32, -0.11, 0.11, 0.32]
    for (tvalue, tlabel, hint), x in zip(targets, x_positions):
        selected = client.rd_target == tvalue
        # Selected = bright green + "[X]" prefix so it reads at a glance;
        # unselected = dim grey-blue with a clearly brighter hover tint so
        # clicks don't look like the same colour dancing around.
        if selected:
            btn_color = color.rgb32(70, 170, 90)
            btn_hl = color.rgb32(100, 210, 120)
            label = f"[X] {tlabel} [{hint}]"
        else:
            btn_color = color.rgb32(45, 55, 75)
            btn_hl = color.rgb32(85, 105, 140)
            label = f"    {tlabel} [{hint}]"
        btn = Button(
            parent=root, text=label,
            position=(x, 0.19), scale=(0.19, 0.06),
            color=btn_color, highlight_color=btn_hl,
        )
        btn.on_click = (lambda v=tvalue: client.rd_set_target(v))

    # Reliability bars per target.
    y = 0.08
    for tvalue, tlabel, _ in targets:
        rel = me.reliability.get(tvalue, 0)
        built = rel >= MIN_RELIABILITY_TO_LAUNCH
        tag = "reliable" if rel >= 75 else ("launch-ready" if built else "not ready")
        tag_color = (110, 200, 120) if rel >= 75 else (
            (240, 200, 90) if built else (220, 90, 90)
        )
        Text(
            text=f"{tlabel:<16} {rel:>3}%   {tag}",
            parent=root, position=(-0.4, y), origin=(-0.5, 0.5),
            scale=1.0, color=color.rgb32(*tag_color),
        )
        y -= 0.05

    # Spend controls.
    minus = Button(
        parent=root, text="-5 MB [Left]",
        position=(-0.15, -0.18), scale=(0.18, 0.055),
        color=color.rgb32(60, 70, 100),
    )
    minus.on_click = lambda: client.rd_change_spend(-5)
    plus = Button(
        parent=root, text="+5 MB [Right]",
        position=(0.15, -0.18), scale=(0.18, 0.055),
        color=color.rgb32(60, 70, 100),
    )
    plus.on_click = lambda: client.rd_change_spend(5)

    Text(
        text=(
            "Queued R&D applies when you SUBMIT at Mission Control.\n"
            "Each 3 MB buys one stochastic R&D roll against the target."
        ),
        parent=root, position=(0, -0.28),
        origin=(0, 0), scale=0.9, color=color.rgb32(140, 150, 170),
    )
    _close_button(client, root, -0.37)
    return root


# ----------------------------------------------------------------------
# Mission Control
# ----------------------------------------------------------------------
def build_mc_panel(client: "BarisClient", parent: Entity) -> Entity:
    me = client.me()
    state = client.state
    root, w, h = _panel_shell(parent, "MISSION CONTROL", title_color=(240, 200, 90))
    if me is None or state is None:
        _close_button(client, root, -0.37)
        return root

    # Top status strip.
    rd_summary = (
        f"R&D: {client.rd_target or '—'}  {client.rd_spend} MB" if client.rd_target
        else "R&D: none queued"
    )
    Text(
        text=(
            f"{state.season.value} {state.year}   Budget {me.budget} MB   "
            f"Prestige {me.prestige}   Programs: {format_programs(me)}"
        ),
        parent=root, position=(-0.42, 0.31),
        origin=(-0.5, 0.5), scale=0.95, color=color.rgb32(220, 225, 235),
    )
    Text(
        text=rd_summary, parent=root,
        position=(-0.42, 0.27), origin=(-0.5, 0.5),
        scale=0.95, color=color.rgb32(160, 200, 160),
    )

    # ---- Mission list (left column) --------------------------------
    visible = visible_missions(me)
    Text(
        text="Available missions (click to queue):",
        parent=root, position=(-0.42, 0.22),
        origin=(-0.5, 0.5), scale=0.95, color=color.rgb32(160, 170, 195),
    )
    y = 0.175
    for m in visible[:10]:
        eff_rocket = effective_rocket(me, m)
        eff_cost = effective_launch_cost(me, m)
        eff_succ = effective_base_success(me, m)
        built = me.rocket_built(eff_rocket)
        mtype = "M" if m.manned else "U"
        queued = client.queued_mission is not None and m.id == client.queued_mission
        marker = "[X]" if queued else ("   " if built else "[!]")
        label = (
            f"{marker} {mtype} {m.name[:18]:<18} "
            f"{rocket_display_name(eff_rocket, me.side)[:10]:<10} "
            f"{eff_cost:>3} MB  {int(eff_succ*100):>3}%"
        )
        if queued:
            fill = color.rgb32(70, 170, 90)
            hl = color.rgb32(100, 210, 120)
        elif built:
            fill = color.rgb32(45, 55, 75)
            hl = color.rgb32(85, 105, 140)
        else:
            fill = color.rgb32(80, 45, 45)   # unavailable — dim red
            hl = color.rgb32(130, 70, 70)
        btn = Button(
            parent=root, text=label,
            position=(-0.22, y), scale=(0.4, 0.032),
            color=fill, highlight_color=hl,
        )
        btn.on_click = (lambda mid=m.id: client.mc_select_mission(mid))
        y -= 0.035

    # ---- Right column: queued mission + briefing -------------------
    Text(
        text="QUEUED", parent=root,
        position=(0.22, 0.22), origin=(0, 0),
        scale=1.05, color=color.rgb32(240, 200, 90),
    )
    if client.queued_mission is None:
        Text(
            text="(no mission queued)",
            parent=root, position=(0.22, 0.16),
            origin=(0, 0), scale=0.95, color=color.rgb32(140, 150, 170),
        )
    else:
        m = MISSIONS_BY_ID[client.queued_mission]
        eff_rocket = effective_rocket(me, m)
        eff_cost = effective_launch_cost(me, m)
        rel_bonus = (
            (me.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
        )
        base = effective_base_success(me, m)
        crew_b = 0.0
        if m.manned:
            active = me.active_astronauts()
            crew_b = _preview_crew_bonus(active, m)
        effective = base + crew_b + rel_bonus

        Text(
            text=f"{m.name}", parent=root,
            position=(0.22, 0.16), origin=(0, 0),
            scale=1.0, color=color.rgb32(240, 220, 180),
        )
        brief = (
            f"Rocket:  {rocket_display_name(eff_rocket, me.side)}\n"
            f"Cost:    {eff_cost} MB\n"
            f"Base:    {base:+.2f}\n"
            f"Crew:    {crew_b:+.2f}\n"
            f"Rel'ty:  {rel_bonus:+.3f}\n"
            f"Eff:     {effective:.2f}  (~{int(max(0, min(1, effective)) * 100)}%)"
        )
        Text(
            text=brief, parent=root,
            position=(0.03, 0.1), origin=(-0.5, 0.5),
            scale=0.9, color=color.rgb32(220, 225, 235),
        )

        # Objective toggles.
        obj_list = objectives_for(m.id)
        if obj_list:
            Text(
                text="Objectives (click to toggle):",
                parent=root, position=(0.22, -0.08),
                origin=(0, 0), scale=0.9, color=color.rgb32(160, 170, 195),
            )
            oy = -0.13
            for obj in obj_list:
                queued = obj.id in client.queued_objectives
                risk = ""
                if obj.fail_ship_loss_chance > 0:
                    risk = f"— {int(obj.fail_ship_loss_chance*100)}% ship loss on fail"
                elif obj.fail_crew_death_chance > 0:
                    risk = f"— {int(obj.fail_crew_death_chance*100)}% crew death on fail"
                marker = "[x]" if queued else "[ ]"
                btn = Button(
                    parent=root,
                    text=f"{marker} {obj.name} {risk}",
                    position=(0.22, oy), scale=(0.4, 0.036),
                    color=(
                        color.rgb32(80, 100, 60) if queued else color.rgb32(34, 44, 70)
                    ),
                )
                btn.on_click = (lambda oid=obj.id: client.mc_toggle_objective(oid))
                oy -= 0.04

    # Architecture (Tier 3 only, one-shot)
    if me.is_tier_unlocked(ProgramTier.THREE) and me.architecture is None:
        Text(
            text="Lunar architecture (one-way choice):",
            parent=root, position=(-0.42, -0.22),
            origin=(-0.5, 0.5), scale=0.95, color=color.rgb32(240, 200, 90),
        )
        ax = -0.32
        for arch in (Architecture.LOR, Architecture.DA, Architecture.EOR, Architecture.LSR):
            btn = Button(
                parent=root, text=arch.value,
                position=(ax, -0.27), scale=(0.085, 0.05),
                color=color.rgb32(70, 80, 100),
            )
            btn.on_click = (lambda a=arch: client.mc_choose_architecture(a))
            ax += 0.11

    # Submit / close
    submit = Button(
        parent=root, text="SUBMIT TURN [Enter]",
        position=(0.25, -0.37), scale=(0.3, 0.058),
        color=color.rgb32(60, 120, 80),
        highlight_color=color.rgb32(90, 170, 110),
    )
    submit.on_click = lambda: client.mc_submit_turn()
    cancel = Button(
        parent=root, text="Close [Esc]",
        position=(-0.25, -0.37), scale=(0.2, 0.05),
        color=color.rgb32(60, 70, 100),
    )
    cancel.on_click = lambda: client.close_current_panel()
    return root


def _preview_crew_bonus(active, mission) -> float:
    from baris.state import CREW_MAX_BONUS, Skill
    if not mission.manned or mission.primary_skill is None:
        return 0.0
    if len(active) < mission.crew_size:
        return 0.0
    skill_key: Skill = mission.primary_skill
    ranked = sorted(active, key=lambda a: a.skill(skill_key), reverse=True)
    crew = ranked[:mission.crew_size]
    avg = sum(a.skill(skill_key) for a in crew) / len(crew)
    return (avg / 100.0) * CREW_MAX_BONUS


# ----------------------------------------------------------------------
# Launch-sequence result panel
# ----------------------------------------------------------------------
def build_result_panel(
    client: "BarisClient", parent: Entity, report: LaunchReport,
) -> Entity:
    me = client.me()
    is_own = bool(me and me.side and report.side == me.side.value)
    title = "YOUR MISSION" if is_own else f"OPPONENT ({report.side})"
    title_color = (240, 200, 90) if is_own else (160, 170, 195)
    root, w, h = _panel_shell(parent, title, width=0.8, height=0.72, title_color=title_color)

    Text(
        text=report.mission_name.upper(),
        parent=root, position=(0, 0.27),
        origin=(0, 0), scale=1.8,
        color=color.rgb32(220, 225, 235),
    )
    Text(
        text=f"{report.username} [{report.side or '?'}]   Rocket: {report.rocket}",
        parent=root, position=(0, 0.22),
        origin=(0, 0), scale=0.9, color=color.rgb32(140, 150, 170),
    )

    if report.aborted:
        banner = "MISSION ABORTED"
        bcolor = (140, 150, 170)
        sub = report.abort_reason or "—"
    elif report.success:
        banner = "MOON LANDING" if report.ended_game else "SUCCESS"
        bcolor = (240, 200, 90) if report.ended_game else (110, 200, 120)
        sub = (
            f"Effective {report.effective_success:.2f}"
            + ("  —  FIRST!" if report.first_claimed else "")
        )
    else:
        banner = "FAILURE"
        bcolor = (220, 90, 90)
        sub = f"Effective {report.effective_success:.2f} — roll did not clear"

    Entity(
        parent=root, model="quad",
        color=color.rgb32(20, 28, 48),
        scale=(0.55, 0.1), y=0.1,
    )
    Text(
        text=banner, parent=root,
        position=(0, 0.1), origin=(0, 0),
        scale=2.4, color=color.rgb32(*bcolor),
    )
    Text(
        text=sub, parent=root,
        position=(0, 0.02), origin=(0, 0),
        scale=0.9, color=color.rgb32(140, 150, 170),
    )

    if not report.aborted:
        details = []
        details.append(f"Prestige       {report.prestige_delta:+d}")
        details.append(f"Reliability    {report.reliability_before}% -> {report.reliability_after}%")
        if report.crew:
            details.append(f"Crew           {', '.join(report.crew)}")
        if report.deaths:
            details.append(f"KIA            {', '.join(report.deaths)}")
        if report.budget_cut:
            details.append(f"Funding cut    {report.budget_cut} MB")
        Text(
            text="\n".join(details), parent=root,
            position=(-0.3, -0.07), origin=(-0.5, 0.5),
            scale=0.95, color=color.rgb32(220, 225, 235),
        )
        if report.objectives:
            obj_y = -0.22
            Text(
                text="Objectives:", parent=root,
                position=(-0.3, obj_y), origin=(-0.5, 0.5),
                scale=0.9, color=color.rgb32(240, 200, 90),
            )
            obj_y -= 0.04
            for obj in report.objectives:
                if obj.skipped:
                    line = f"  - {obj.name}: skipped ({obj.skip_reason})"
                    col = (140, 150, 170)
                elif obj.ship_lost:
                    line = f"  - {obj.name}: CATASTROPHIC — KIA {', '.join(obj.deaths) or '?'}"
                    col = (220, 90, 90)
                elif obj.success:
                    line = f"  - {obj.name}: {obj.performer} succeeded ({obj.prestige_delta:+d})"
                    col = (110, 200, 120)
                elif obj.deaths:
                    line = f"  - {obj.name}: {', '.join(obj.deaths)} lost ({obj.prestige_delta:+d})"
                    col = (220, 90, 90)
                else:
                    line = f"  - {obj.name}: failed (no casualties)"
                    col = (140, 150, 170)
                Text(
                    text=line, parent=root,
                    position=(-0.3, obj_y), origin=(-0.5, 0.5),
                    scale=0.85, color=color.rgb32(*col),
                )
                obj_y -= 0.035

    cont = Button(
        parent=root, text="Continue [Space]",
        position=(0, -0.32), scale=(0.3, 0.055),
        color=color.rgb32(60, 80, 120),
    )
    cont.on_click = lambda: client.advance_result_panel()
    return root
