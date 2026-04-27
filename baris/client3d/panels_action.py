"""Gameplay panels for the 3D client: R&D Complex, Mission Control,
and the post-launch result panel shown during the launch sequence."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ursina import Button, Entity, Text, color, invoke

from baris.resolver import (
    crew_compatibility_bonus,
    effective_base_success,
    effective_launch_cost,
    effective_lunar_modifier,
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
    PHASE_OUTCOME_FAIL,
    PHASE_OUTCOME_PARTIAL,
    PHASE_OUTCOME_PASS,
    PHASE_OUTCOME_SKIP,
    ProgramTier,
    RELIABILITY_SWING_PER_POINT,
    Rocket,
    objectives_for,
    phase_outcomes,
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
        origin=(0, 0), z=-0.01, scale=1.1, color=color.rgb32(220, 225, 235),
    )

    # Target buttons. Row 1 is the three rocket classes; row 2 is the
    # six module / component R&D tracks. Phase Q split components out
    # so the row-2 grid is denser than V1's single Docking entry.
    rocket_targets: list[tuple[str, str]] = [
        (Rocket.LIGHT.value,  rocket_display_name(Rocket.LIGHT, me.side)),
        (Rocket.MEDIUM.value, rocket_display_name(Rocket.MEDIUM, me.side)),
        (Rocket.HEAVY.value,  rocket_display_name(Rocket.HEAVY, me.side)),
    ]
    module_targets: list[tuple[str, str]] = [
        (m.value, m.value) for m in Module
    ]
    all_targets = rocket_targets + module_targets

    def _draw_target_row(items, y, scale_x):
        if not items:
            return
        n = len(items)
        spacing = 0.86 / max(n, 1)
        first_x = -0.43 + spacing / 2
        for i, (tvalue, tlabel) in enumerate(items):
            x = first_x + i * spacing
            selected = client.rd_target == tvalue
            if selected:
                btn_color = color.rgb32(70, 170, 90)
                btn_hl = color.rgb32(100, 210, 120)
                label = f"[X] {tlabel}"
            else:
                btn_color = color.rgb32(45, 55, 75)
                btn_hl = color.rgb32(85, 105, 140)
                label = tlabel
            btn = Button(
                parent=root, text=label,
                position=(x, y, -0.02), scale=(scale_x, 0.055),
                color=btn_color, highlight_color=btn_hl,
            )
            btn.on_click = (lambda v=tvalue: client.rd_set_target(v))

    _draw_target_row(rocket_targets, 0.22, scale_x=0.24)
    _draw_target_row(module_targets, 0.155, scale_x=0.13)

    # Reliability bars per target + per-row action buttons.
    # R-deep — each row shows class research %, unit count, and the
    # next ACTIVE unit's reliability. Three buttons per row:
    #   BUILD — pay HARDWARE_UNIT_COST to mint a new unit at the
    #           current class reliability.
    #   MAX-Q — cheap, no-risk test on the next ACTIVE unit.
    #   FULL  — pricier test with FULL_UP_LOSS_CHANCE of destroying
    #           the article, but a bigger reliability gain.
    from baris.state import (
        FULL_UP_TEST_COST, HARDWARE_UNIT_COST, MAX_Q_TEST_COST,
    )
    y = 0.085
    for tvalue, tlabel in all_targets:
        rel = me.reliability.get(tvalue, 0)
        built = rel >= MIN_RELIABILITY_TO_LAUNCH
        active = me.active_units(tvalue)
        n_active = len(active)
        next_rel = active[0].reliability if active else rel
        tag = "reliable" if rel >= 75 else ("launch-ready" if built else "not ready")
        tag_color = (110, 200, 120) if rel >= 75 else (
            (240, 200, 90) if built else (220, 90, 90)
        )
        Text(
            text=(
                f"{tlabel:<16} R&D {rel:>3}%   "
                f"units {n_active}  next {next_rel:>3}%   {tag}"
            ),
            parent=root, position=(-0.43, y), origin=(-0.5, 0.5), z=-0.01,
            scale=0.7, color=color.rgb32(*tag_color),
        )
        build_btn = Button(
            parent=root, text=f"BUILD {HARDWARE_UNIT_COST}",
            position=(0.20, y, -0.02), scale=(0.10, 0.028),
            color=color.rgb32(70, 90, 100),
            highlight_color=color.rgb32(100, 130, 150),
        )
        build_btn.on_click = (lambda v=tvalue: client.rd_build_hardware(v))
        maxq_btn = Button(
            parent=root, text=f"MAX-Q {MAX_Q_TEST_COST}",
            position=(0.31, y, -0.02), scale=(0.10, 0.028),
            color=color.rgb32(80, 100, 70),
            highlight_color=color.rgb32(110, 150, 90),
        )
        maxq_btn.on_click = (lambda v=tvalue: client.rd_run_max_q_test(v))
        full_btn = Button(
            parent=root, text=f"FULL {FULL_UP_TEST_COST}",
            position=(0.42, y, -0.02), scale=(0.10, 0.028),
            color=color.rgb32(120, 80, 70),
            highlight_color=color.rgb32(160, 100, 90),
        )
        full_btn.on_click = (lambda v=tvalue: client.rd_run_full_up_test(v))
        y -= 0.034

    # Spend controls.
    minus = Button(
        parent=root, text="-5 MB [Left]",
        position=(-0.15, -0.18, -0.02), scale=(0.18, 0.055),
        color=color.rgb32(60, 70, 100),
    )
    minus.on_click = lambda: client.rd_change_spend(-5)
    plus = Button(
        parent=root, text="+5 MB [Right]",
        position=(0.15, -0.18, -0.02), scale=(0.18, 0.055),
        color=color.rgb32(60, 70, 100),
    )
    plus.on_click = lambda: client.rd_change_spend(5)

    Text(
        text=(
            "Queued R&D applies when you SUBMIT at Mission Control.\n"
            "Each 3 MB buys one stochastic R&D roll against the target."
        ),
        parent=root, position=(0, -0.28),
        origin=(0, 0), z=-0.01, scale=0.9, color=color.rgb32(140, 150, 170),
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
        origin=(-0.5, 0.5), z=-0.01, scale=0.95, color=color.rgb32(220, 225, 235),
    )
    Text(
        text=rd_summary, parent=root,
        position=(-0.42, 0.27), origin=(-0.5, 0.5), z=-0.01,
        scale=0.95, color=color.rgb32(160, 200, 160),
    )

    # Per-pad manifest banner — summarises A/B/C slots so the player can
    # see what's assembled where at a glance.
    scheduled = me.scheduled_launch   # back-compat: first booked pad
    pad_bits: list[str] = []
    for pad in me.pads:
        if pad.damaged:
            pad_bits.append(f"{pad.pad_id}:REP {pad.repair_turns_remaining}")
            continue
        if pad.scheduled_launch is None:
            pad_bits.append(f"{pad.pad_id}:idle")
            continue
        try:
            name = MISSIONS_BY_ID[MissionId(pad.scheduled_launch.mission_id)].name
        except (ValueError, KeyError):
            name = pad.scheduled_launch.mission_id
        pad_bits.append(f"{pad.pad_id}:{name[:14]}")
    Text(
        text="PADS: " + "   ".join(pad_bits),
        parent=root, position=(-0.42, 0.235), origin=(-0.5, 0.5), z=-0.01,
        scale=0.95, color=color.rgb32(240, 200, 90),
    )

    # ---- Mission list (left column) --------------------------------
    visible = visible_missions(me)
    Text(
        text="Available missions (click to queue):",
        parent=root, position=(-0.42, 0.22),
        origin=(-0.5, 0.5), z=-0.01, scale=0.95, color=color.rgb32(160, 170, 195),
    )
    y = 0.175
    for m in visible[:10]:
        eff_rocket = effective_rocket(me, m)
        eff_cost = effective_launch_cost(me, m)
        eff_succ = effective_base_success(me, m)
        built = me.rocket_built(eff_rocket)
        from baris.resolver import missing_modules
        missing_mods = missing_modules(me, m)
        mtype = "M" if m.manned else "U"
        queued = client.queued_mission is not None and m.id == client.queued_mission
        # [X] queued, [!] hardware blocker (rocket OR required module),
        # blank when ready.
        if queued:
            marker = "[X]"
        elif not built or missing_mods:
            marker = "[!]"
        else:
            marker = "   "
        label = (
            f"{marker} {mtype} {m.name[:18]:<18} "
            f"{rocket_display_name(eff_rocket, me.side)[:10]:<10} "
            f"{eff_cost:>3} MB  {int(eff_succ*100):>3}%"
        )
        if queued:
            fill = color.rgb32(70, 170, 90)
            hl = color.rgb32(100, 210, 120)
        elif built and not missing_mods:
            fill = color.rgb32(45, 55, 75)
            hl = color.rgb32(85, 105, 140)
        else:
            fill = color.rgb32(80, 45, 45)   # unavailable — dim red
            hl = color.rgb32(130, 70, 70)
        btn = Button(
            parent=root, text=label,
            position=(-0.22, y, -0.02), scale=(0.4, 0.032),
            color=fill, highlight_color=hl,
        )
        btn.on_click = (lambda mid=m.id: client.mc_select_mission(mid))
        y -= 0.035

    # ---- Right column: queued mission + briefing -------------------
    Text(
        text="QUEUED", parent=root,
        position=(0.22, 0.22), origin=(0, 0), z=-0.01,
        scale=1.05, color=color.rgb32(240, 200, 90),
    )
    if client.queued_mission is None:
        Text(
            text="(no mission queued)",
            parent=root, position=(0.22, 0.16),
            origin=(0, 0), z=-0.01, scale=0.95, color=color.rgb32(140, 150, 170),
        )
    else:
        from baris.resolver import component_reliability_bonus
        m = MISSIONS_BY_ID[client.queued_mission]
        eff_rocket = effective_rocket(me, m)
        eff_cost = effective_launch_cost(me, m)
        rel_bonus = (
            (me.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
        )
        comp_b = component_reliability_bonus(me, m)
        base = effective_base_success(me, m)
        crew_b = 0.0
        compat_b = 0.0
        if m.manned:
            active = me.active_astronauts()
            preview_crew = _preview_crew_selection(active, m)
            if preview_crew:
                crew_b = _preview_crew_bonus(preview_crew, m)
                compat_b = crew_compatibility_bonus(preview_crew)
        recon_bonus, lm_penalty = effective_lunar_modifier(me, m)
        effective = (
            base + crew_b + compat_b + rel_bonus + comp_b
            + recon_bonus - lm_penalty
        )

        Text(
            text=f"{m.name}", parent=root,
            position=(0.22, 0.16), origin=(0, 0), z=-0.01,
            scale=1.0, color=color.rgb32(240, 220, 180),
        )
        lunar_line = ""
        if recon_bonus > 0 or lm_penalty > 0:
            lunar_line = (
                f"Recon:   {recon_bonus:+.3f}\n"
                f"LM:      {-lm_penalty:+.3f}\n"
            )
        compat_line = f"Compat:  {compat_b:+.3f}\n" if compat_b else ""
        comp_line = f"Comp:    {comp_b:+.3f}\n" if comp_b else ""
        # Pad assignment preview — server picks the first available pad
        # at resolve time, so report what that would be right now.
        next_pad = me.available_pad()
        if next_pad is not None:
            pad_line = f"Pad:     {next_pad.pad_id}\n"
        else:
            pad_line = "Pad:     ALL BUSY — won't fly\n"
        brief = (
            f"Rocket:  {rocket_display_name(eff_rocket, me.side)}\n"
            f"Cost:    {eff_cost} MB\n"
            f"{pad_line}"
            f"Base:    {base:+.2f}\n"
            f"Crew:    {crew_b:+.2f}\n"
            f"{compat_line}"
            f"Rel'ty:  {rel_bonus:+.3f}\n"
            f"{comp_line}"
            f"{lunar_line}"
            f"Eff:     {effective:.2f}  (~{int(max(0, min(1, effective)) * 100)}%)"
        )
        Text(
            text=brief, parent=root,
            position=(0.03, 0.1), origin=(-0.5, 0.5), z=-0.01,
            scale=0.9, color=color.rgb32(220, 225, 235),
        )

        # Objective toggles.
        obj_list = objectives_for(m.id)
        oy = -0.13
        if obj_list:
            Text(
                text="Objectives (click to toggle):",
                parent=root, position=(0.22, -0.08),
                origin=(0, 0), z=-0.01, scale=0.9, color=color.rgb32(160, 170, 195),
            )
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
                    position=(0.22, oy, -0.02), scale=(0.4, 0.036),
                    color=(
                        color.rgb32(80, 100, 60) if queued else color.rgb32(34, 44, 70)
                    ),
                )
                btn.on_click = (lambda oid=obj.id: client.mc_toggle_objective(oid))
                oy -= 0.04

        # Phase O — manual crew assignment. Inline picker beneath the
        # objectives column, only for manned missions. Empty list is
        # the legacy "auto-pick top-skilled" default. Per-seat roles
        # render as a small "[1] CAPSULE [2] LM_PILOT [3] EVA" banner.
        if m.manned:
            from baris.state import Skill, character_portrait
            roles: list[Skill] = list(m.crew_roles) if m.crew_roles else []
            if not roles and m.primary_skill is not None:
                roles = [m.primary_skill] * m.crew_size
            cy = oy - 0.02
            Text(
                text=(
                    f"Crew — pick {m.crew_size} (or leave empty for "
                    "auto top-skilled):"
                ),
                parent=root, position=(0.22, cy),
                origin=(0, 0), z=-0.01, scale=0.85, color=color.rgb32(160, 170, 195),
            )
            cy -= 0.025
            if roles:
                role_text = "  ".join(
                    f"[{i + 1}] {r.value}" for i, r in enumerate(roles)
                )
                Text(
                    text=role_text,
                    parent=root, position=(0.22, cy),
                    origin=(0, 0), z=-0.01, scale=0.7,
                    color=color.rgb32(140, 160, 195),
                )
                cy -= 0.025
            pool = [a for a in me.astronauts if a.flight_ready]
            next_slot = len(client.queued_crew)
            col_role = roles[next_slot] if next_slot < len(roles) else (
                roles[0] if roles else None
            )
            from baris.client3d.text_utils import panda_glyph
            for astro in pool[:8]:
                picked = astro.id in client.queued_crew
                marker = "[x]" if picked else "[ ]"
                glyph_raw, _ = character_portrait(astro.name)
                glyph = panda_glyph(glyph_raw, astro.name)
                col_value = astro.skill(col_role) if col_role else 0
                col_label = col_role.value[:3] if col_role else "skl"
                btn = Button(
                    parent=root,
                    text=f"{marker} {glyph} {astro.name[:14]}  {col_label} {col_value}",
                    position=(0.22, cy, -0.02), scale=(0.4, 0.034),
                    color=(
                        color.rgb32(80, 100, 60) if picked else color.rgb32(34, 44, 70)
                    ),
                )
                btn.on_click = (lambda aid=astro.id: client.mc_toggle_crew(aid))
                cy -= 0.038

    # Architecture (Tier 3 only, one-shot)
    if me.is_tier_unlocked(ProgramTier.THREE) and me.architecture is None:
        Text(
            text="Lunar architecture (one-way choice):",
            parent=root, position=(-0.42, -0.22),
            origin=(-0.5, 0.5), z=-0.01, scale=0.95, color=color.rgb32(240, 200, 90),
        )
        ax = -0.32
        for arch in (Architecture.LOR, Architecture.DA, Architecture.EOR, Architecture.LSR):
            btn = Button(
                parent=root, text=arch.value,
                position=(ax, -0.27, -0.02), scale=(0.085, 0.05),
                color=color.rgb32(70, 80, 100),
            )
            btn.on_click = (lambda a=arch: client.mc_choose_architecture(a))
            ax += 0.11

    # Submit / scrub / close
    submit = Button(
        parent=root, text="SUBMIT TURN [Enter]",
        position=(0.28, -0.37, -0.02), scale=(0.28, 0.058),
        color=color.rgb32(60, 120, 80),
        highlight_color=color.rgb32(90, 170, 110),
    )
    submit.on_click = lambda: client.mc_submit_turn()
    # SCRUB is only meaningful when a scheduled launch exists; otherwise
    # render it dim so the player knows what state it controls.
    if scheduled is not None:
        scrub_color = color.rgb32(170, 60, 60)
        scrub_hl = color.rgb32(220, 90, 90)
    else:
        scrub_color = color.rgb32(70, 55, 55)
        scrub_hl = color.rgb32(100, 80, 80)
    scrub = Button(
        parent=root, text="SCRUB",
        position=(0.00, -0.37, -0.02), scale=(0.18, 0.058),
        color=scrub_color, highlight_color=scrub_hl,
    )
    scrub.on_click = lambda: client.mc_scrub_scheduled()
    cancel = Button(
        parent=root, text="Close [Esc]",
        position=(-0.28, -0.37, -0.02), scale=(0.2, 0.05),
        color=color.rgb32(60, 70, 100),
    )
    cancel.on_click = lambda: client.close_current_panel()
    return root


def _preview_crew_selection(active, mission) -> list:
    if not mission.manned or mission.primary_skill is None:
        return []
    if len(active) < mission.crew_size:
        return []
    ranked = sorted(active, key=lambda a: a.skill(mission.primary_skill), reverse=True)
    return ranked[:mission.crew_size]


def _preview_crew_bonus(crew, mission) -> float:
    from baris.state import CREW_MAX_BONUS
    if not crew or mission.primary_skill is None:
        return 0.0
    avg = sum(a.skill(mission.primary_skill) for a in crew) / len(crew)
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
        origin=(0, 0), scale=1.8, z=-0.01,
        color=color.rgb32(220, 225, 235),
    )
    # R-deep — show the specific unit that flew so the player can see
    # which article was consumed and at what reliability.
    rocket_line = f"Rocket: {report.rocket}"
    if report.unit_id:
        rocket_line = (
            f"Rocket: {report.rocket}  "
            f"({report.unit_id} @ {report.unit_reliability}%)"
        )
    Text(
        text=f"{report.username} [{report.side or '?'}]   {rocket_line}",
        parent=root, position=(0, 0.22),
        origin=(0, 0), scale=0.9, z=-0.01,
        color=color.rgb32(140, 150, 170),
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
    elif report.partial:
        # P-deep — partial-success path: phase failed but the casualty
        # roll cleared, so the crew came home and a slice of prestige
        # was awarded. Distinct yellow banner so the player can tell
        # this from a hard FAILURE at a glance.
        banner = "PARTIAL"
        bcolor = (240, 200, 90)
        if report.failed_phase:
            sub = (
                f"{report.abort_label or 'aborted'} after {report.failed_phase}  "
                f"(eff {report.effective_success:.2f})"
            )
        else:
            sub = report.abort_label or "mission aborted, crew safe"
    else:
        banner = "FAILURE"
        bcolor = (220, 90, 90)
        # Phase P — surface the failed phase in the sub-line for cinematic
        # weight ("lost on Trans-lunar injection") rather than a generic
        # "roll did not clear".
        if report.failed_phase:
            sub = (
                f"Lost during {report.failed_phase}  "
                f"(eff {report.effective_success:.2f})"
            )
        else:
            sub = f"Effective {report.effective_success:.2f} — roll did not clear"

    # Drop any previous-panel's quad backdrop here — an overlapping
    # Entity(model="quad") at the same z as the shell background z-fights
    # and sometimes wins, covering the banner text. The banner color alone
    # is enough to read against the panel's dark blue. All content-text
    # entities below also carry z=-0.01 so they render a hair in front of
    # the shell background (which sits at z=0) regardless of creation-
    # order quirks.
    Text(
        text=banner, parent=root,
        position=(0, 0.1), origin=(0, 0),
        scale=2.4, z=-0.01, color=color.rgb32(*bcolor),
    )
    Text(
        text=sub, parent=root,
        position=(0, 0.02), origin=(0, 0),
        scale=0.9, z=-0.01, color=color.rgb32(140, 150, 170),
    )

    if not report.aborted:
        details = []
        details.append(f"Prestige       {report.prestige_delta:+d}")
        details.append(f"Reliability    {report.reliability_before}% -> {report.reliability_after}%")
        if report.lunar_recon_bonus > 0:
            details.append(f"Recon bonus    +{report.lunar_recon_bonus:.3f}")
        if report.lm_points_penalty > 0:
            details.append(f"LM penalty     -{report.lm_points_penalty:.3f}")
        if report.crew:
            details.append(f"Crew           {', '.join(report.crew)}")
        if report.deaths:
            details.append(f"KIA            {', '.join(report.deaths)}")
        if report.budget_cut:
            details.append(f"Funding cut    {report.budget_cut} MB")
        Text(
            text="\n".join(details), parent=root,
            position=(-0.3, -0.07), origin=(-0.5, 0.5),
            scale=0.95, z=-0.01, color=color.rgb32(220, 225, 235),
        )
        if report.objectives:
            obj_y = -0.22
            Text(
                text="Objectives:", parent=root,
                position=(-0.3, obj_y), origin=(-0.5, 0.5),
                scale=0.9, z=-0.01, color=color.rgb32(240, 200, 90),
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
                    scale=0.85, z=-0.01, color=color.rgb32(*col),
                )
                obj_y -= 0.035

        # Cinematic phase ticker — right-hand column reveals each
        # mission phase one at a time so the report reads like a
        # mini-replay of the flight rather than a static verdict.
        phase_rows = phase_outcomes(report)
        if phase_rows:
            phase_x = 0.18
            Text(
                text="MISSION TIMELINE", parent=root,
                position=(phase_x, -0.07), origin=(-0.5, 0.5),
                scale=0.95, z=-0.01, color=color.rgb32(240, 200, 90),
            )
            cy = -0.11
            step = 0.55
            for i, (phase_name, outcome) in enumerate(phase_rows):
                row = Text(
                    text="", parent=root,
                    position=(phase_x, cy), origin=(-0.5, 0.5),
                    scale=0.85, z=-0.01,
                    color=color.rgb32(60, 65, 80),
                )
                if outcome == PHASE_OUTCOME_PASS:
                    line, tone = f"+  {phase_name}", (110, 200, 120)
                elif outcome == PHASE_OUTCOME_FAIL:
                    line, tone = f"X  {phase_name}", (220, 90, 90)
                elif outcome == PHASE_OUTCOME_PARTIAL:
                    # P-deep — yellow ! for the recoverable abort point.
                    line, tone = f"!  {phase_name}", (240, 200, 90)
                else:
                    line, tone = f"-  {phase_name}", (110, 110, 130)

                def _reveal(r=row, l=line, t=tone) -> None:
                    if r:
                        r.text = l
                        r.color = color.rgb32(*t)
                invoke(_reveal, delay=i * step)
                cy -= 0.035

    cont = Button(
        parent=root, text="Continue [Space]",
        position=(0, -0.32, -0.02), scale=(0.3, 0.055),
        color=color.rgb32(60, 80, 120),
    )
    cont.on_click = lambda: client.advance_result_panel()
    return root
