# Plan: defaults the driver names, and acquisition settings that only say how to trigger

Status: agreed with Thom on 2026-10-14. D1–D3 settled as recommended. Step 1 (controller 0.3.0,
mock, docs, tutorials) built on 2026-10-14 without the external review, at Thom's choice; steps 2–4
(interface, drivers, assembly) followed on 2026-10-14: step 2 (interface, cf3ce24) and step 3
(drivers 021018c Leica in full, 74b3451 Nikon, ZEISS and mesoSPIM only what the driver check asks,
by Thom's choice) pushed to release-candidate. Step 4 (assembly pins) and the move to main open. The mock's second trigger is called `full`, not `recipe`
(Thom). D1 as built: the workflow gives the whole convention stem
`{acquisition_type}_{run hash}_{label}` and a rerun in the run gets `_001`.

Built differently from the text below in one place: the controller, not each driver, fills in the
default actuator. It reads `get_actuators`, refuses an unknown axis or motor before the driver is
asked, and hands the driver a motor for every axis. The mock, an older module-style driver, still
applies its own default.

## Why

Two things in the contract are said by convention instead of by the driver:

1. **The default actuator** is "the first motor `get_actuators` lists". Nothing names it, nothing
   checks it, and no answer shows which motor was used.
2. **Acquisition settings** have grown into four kinds of things: how a capture is triggered,
   the microscope's state (z planes, z step, exposure, zoom, optical configuration), saving
   (folder, format, save_to, source, projection, cleanup), and driver mechanics (backlash,
   timeouts). Their `default` is optional.

Thom's rule: the driver decides the defaults, and the contract communicates them. Acquisition
settings are about how to trigger an acquisition, nothing else; z and the like are state.

## What changes

### 1. `get_actuators` names its default per axis

```python
{'x': {'options': ['motoric'], 'default': 'motoric'},
 'y': {'options': ['motoric'], 'default': 'motoric'},
 'z': {'options': ['motoric', 'piezo'], 'default': 'motoric'}}
```

- The driver returns this shape; list order means nothing.
- `validate_driver` refuses an axis without `default`, or a `default` not in `options`.
- `get_xyz` and `set_xyz` use the same rule: an axis left out of `with_actuators` uses its
  `default`. Both docs say so at both calls.
- Each axis in a `get_xyz`/`set_xyz` answer carries `'actuator': <the one used>` beside
  `position`, so the default shows in every answer, not only in the text.

### 2. Acquisition settings hold the trigger, and every setting has a default

```python
{'trigger': {'options': ['snap', 'full'], 'default': 'snap', 'active': 'snap'}}
```

- `snap`: one picture with exactly what is set now.
- `full`: run the whole acquisition the vendor software has stored and selected (a Leica job, a
  ZEISS experiment, an NIS ND acquisition, a mesoSPIM acquisition row); the recipe carries its
  own stack, channels, and so on.
- A driver lists only the triggers its microscope has. It may add one of its own (for example a
  hardware trigger), named and described. `default` is required on every setting;
  `validate_driver` refuses one without it, or a listed `default` not in its `options`.
- `active` stays: what `acquire` uses when given nothing.

### 3. Everything else leaves acquisition settings

| Was | Goes to |
|---|---|
| z planes, z step, z start/end, exposure, zoom, shutter, optical configuration | `get_state` / `set_state` (`changeable`) |
| which job / experiment is selected | `get_state` / `set_state`; the trigger only says "run the selected recipe" |
| backlash, rounds, timeouts, cleanup, source | the driver's own profile and configuration |
| format, save location | set up once per microscope in the driver's setup, reported as `setup` items (see D3) |
| folder | see decision D1 |

## Decisions still open

- **D1, the acquisition type in the file name.** The naming convention begins
  `{acquisition_type}_{hash6}_{position_label}_...`, and today `acquisition_type` reaches the
  driver as the `folder` setting. With `folder` gone, it needs another way in.
  Recommendation: the workflow puts it at the start of the label it passes
  (`overview_K00_M000000_G000000_P000001_V00`); the driver adds hash and T/C/Z and never parses
  the label. The interface's mover keeps moving files unrenamed.
- **D2, format.** One fixed per driver (written by the naming convention) or set up per
  microscope. Recommendation: set up per microscope, reported in `get_info`'s `setup`.
- **D3, `output_root` leaves `get_info`.** Thom: it feels like overfitting to the interface. The
  controller never uses it; only the interface does, to place its run folder, and it repeats the
  data location `setup` already states. `acquire` already lists where every file landed, and the
  interface moves them into its run (`move_record_images`). Recommendation: `get_info` answers
  `description` and `setup` only; the driver's save location is a `setup` item in words; the
  interface takes its run folder from its own setting (the launcher's `--output-root`, already
  passed into the connection in `connecting.py`) and refuses a run without one, instead of
  asking the driver. Cost: a run folder on another drive than the driver's turns every move
  into a copy; each computer avoids that by choosing the same drive.

## What it touches

- **Controller** (contract 0.2.0 → 0.3.0): `zmart_controller.py`, `validate.py`
  (`check_*` for actuators and settings; `get_info` without `output_root`), `template/zmart_driver.py`, the mock plugin, both
  READMEs and both tutorials, tests in `tests/controller_tests` and `tests/mock_tests`.
- **Drivers**: Leica (adapter + plugin + unit tests), Nikon, ZEISS, mesoSPIM: `get_actuators`
  shape, `get_acquisition_settings` reduced to `trigger`, the removed settings moved to state or
  configuration, `driver-anatomy.md` and each README. (Earlier choices said ZEISS and mesoSPIM
  may be left behind; for a contract change they must at least still validate, or be marked.)
- **Interface**: `framework/bridge/connecting.py` (run folder from its own setting, not
  `get_info`), `parts/microscope/instrument.py` (`folder` hand-off), `live.js`, `mock.js`,
  `backend-contract.js`, the mock microscope (`driver.py`, its plugin, tests), the bridge's
  `readings.py`, and the focussing step, which today gets its stack from the job it selects.
- **Assembly** (`ZMART-microscopy`): pins move to controller 0.3.0.

## Order

1. Controller: failing tests for both shapes and the validator, then the change, the mock,
   the docs. Tag 0.3.0 on `release-candidate`.
2. Interface mock microscope and interface, against controller 0.3.0; walk.spec on the mock.
3. Drivers, one at a time, each with its unit tests; Leica first.
4. Assembly pins; full suites once, at the end.

## Review prompt

> You are reviewing a planned contract change to the ZMART Controller
> (github.com/thomdehoog/ZMART-controller, branch `release-candidate`), a vendor-neutral Python
> layer between microscope workflows and per-microscope drivers. Read
> `docs/plan-defaults-and-the-trigger.md`, then `zmart_controller/zmart_controller.py`,
> `zmart_controller/validate.py`, `zmart_controller/template/zmart_driver.py`,
> `zmart_controller/mock/zmart_controller_plugin.py` and the two READMEs under `docs/`.
>
> Judge the plan, not the current code. In particular:
> 1. Is `{'options': [...], 'default': ...}` per axis the right way for a driver to declare its
>    default actuator? Is echoing `'actuator'` in every `get_xyz`/`set_xyz` answer worth it?
> 2. Can every acquisition really be described as a trigger (`snap`, `recipe`, driver-defined)
>    once z, exposure and job selection move to state? Name a real microscope workflow
>    (confocal, widefield, light-sheet, slide scanner) this would break, if any.
> 3. Is "which recipe is selected" correctly state rather than an acquisition setting?
> 4. D1 and D2: is putting the acquisition type at the start of `position_label` clean, or does
>    it leak a workflow concept into the driver? Propose a better seam if there is one.
> 5. D3: is removing `output_root` from `get_info` sound, or does some workflow genuinely need
>    the driver to say where it saves before the first capture?
> 6. What does the plan miss: validator rules, migration of existing drivers, the interface's
>    focussing step, anything that would make a driver author guess.
>
> Answer with concrete findings, each with the file or call it concerns and what you would do.
> Do not rewrite the plan.
