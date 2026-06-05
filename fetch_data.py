#!/usr/bin/env python3
"""
Sensibo Climate Data Fetcher
Fetches:
  - Temperature & humidity (historicalMeasurements)
  - AC on/off events  → calculates daily kWh and cost in ₪

User config (edit the two lines below):
  AC_POWER_KW    – your AC's rated power in kilowatts (check the label/manual)
  PRICE_PER_KWH  – electricity price in ₪ per kWh (Israel average ~0.65)
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

API_KEY       = os.environ.get("SENSIBO_API_KEY")
DATA_FILE     = Path("data/measurements.json")
ENERGY_FILE   = Path("data/energy.json")
CONFIG_FILE   = Path("config.json")
BASE_URL      = "https://home.sensibo.com/api/v2"


# ─── CONFIG ───────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def get_device_power(config, room_name):
    """Return power_kw for a device by room name, falling back to default."""
    devices = config.get("devices", {})
    if room_name in devices:
        return float(devices[room_name].get("power_kw", config.get("default_power_kw", 2.5)))
    return float(config.get("default_power_kw", 2.5))


# ── DEVICES ───────────────────────────────────────────────

def get_devices():
    resp = requests.get(
        f"{BASE_URL}/users/me/pods",
        params={"apiKey": API_KEY, "fields": "id,room,measurements"}
    )
    resp.raise_for_status()
    return resp.json()["result"]


# ── TEMPERATURE / HUMIDITY ────────────────────────────────

def get_measurements(device_id, days_back=2):
    """
    Sensibo v2 returns measurements inside the pod object itself.
    historicalMeasurements endpoint requires a paid plan on some accounts.
    We use the pods endpoint with measurements field instead.
    """
    start = datetime.now(timezone.utc) - timedelta(days=days_back)
    all_items = []

    # Try historicalMeasurements — Sensibo returns data per-minute for recent period
    try:
        resp = requests.get(
            f"{BASE_URL}/pods/{device_id}/historicalMeasurements",
            params={"apiKey": API_KEY, "fields": "temperature,humidity,time",
                    "limit": 100, "offset": 0}
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})
        # result can be a list, or a dict with "measurements" key
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("measurements", [])
            # Sometimes result IS the measurements dict (not wrapped)
            if not items and result.get("temperature") is not None:
                items = [result]
        else:
            items = []
        print(f"  historicalMeasurements returned {len(items)} items")
        for item in items:
            ts_str = _extract_ts(item)
            if not ts_str:
                continue
            try:
                ts = _parse_ts(ts_str)
            except Exception:
                continue
            if ts >= start:
                all_items.append({
                    "ts":          ts_str,
                    "temperature": item.get("temperature"),
                    "humidity":    item.get("humidity"),
                })
        if all_items:
            print(f"  Got {len(all_items)} measurements from history.")
            return all_items
    except Exception as e:
        print(f"  historicalMeasurements failed: {e}")

    # Fallback: current measurement from pod object (saves 1 point per run)
    print("  Falling back to current measurement from pod...")
    resp = requests.get(
        f"{BASE_URL}/users/me/pods",
        params={"apiKey": API_KEY, "fields": "id,measurements"}
    )
    resp.raise_for_status()
    for pod in resp.json().get("result", []):
        if pod.get("id") == device_id:
            entry = _measurement_from_pod(pod)
            if entry:
                print(f"  Current measurement: temp={entry['temperature']} hum={entry['humidity']}")
                all_items.append(entry)

            break
    return all_items


# ── AC STATE EVENTS → ENERGY ──────────────────────────────

def get_ac_events(device_id, days_back=2):
    """
    Fetch AC state-change events (on/off).
    Event type 1000000 = AC State Changed.
    Returns list of {"ts": ..., "on": bool} sorted oldest→newest.
    """
    start = datetime.now(timezone.utc) - timedelta(days=days_back)
    resp = requests.get(
        f"{BASE_URL}/pods/{device_id}/events",
        params={
            "apiKey":    API_KEY,
            "eventType": 1000000,
            "limit":     500,
        }
    )
    resp.raise_for_status()
    raw = resp.json().get("result", [])

    events = []
    for ev in raw:
        # Real API: timestamp is top-level, acState is inside details{}
        ts_str = ev.get("timestamp") or ev.get("ts") or ev.get("createdAt") or ""
        if not ts_str:
            continue
        try:
            ts = _parse_ts(ts_str)
        except Exception:
            continue
        if ts < start:
            continue
        # acState lives inside details{}
        details = ev.get("details", {})
        ac_on = details.get("acState", {}).get("on")
        if ac_on is None:
            ac_on = ev.get("acState", {}).get("on")
        if ac_on is not None:
            events.append({"ts": ts, "on": bool(ac_on)})

    events.sort(key=lambda x: x["ts"])
    return events


def compute_daily_energy(events, power_kw, price_per_kwh, days_back=2):
    """
    Given a list of {"ts": datetime, "on": bool} events,
    compute kWh and cost per calendar day (local Israel time UTC+3).
    Returns {date_str: {"kwh": float, "cost_ils": float, "minutes_on": int}}
    """
    TZ_OFFSET = timedelta(hours=3)  # Israel Standard Time (no DST in calculation)
    result = {}

    # Initialise all days in window
    today_local = (datetime.now(timezone.utc) + TZ_OFFSET).date()
    for d in range(days_back + 1):
        ds = str(today_local - timedelta(days=d))
        result[ds] = {"kwh": 0.0, "cost_ils": 0.0, "minutes_on": 0}

    if not events:
        return result

    # Walk pairs of on→off
    prev_on_ts = None
    for ev in events:
        if ev["on"]:
            prev_on_ts = ev["ts"]
        else:
            if prev_on_ts is None:
                continue
            # AC was on from prev_on_ts until ev["ts"]
            _add_duration(result, prev_on_ts, ev["ts"], power_kw, price_per_kwh, TZ_OFFSET)
            prev_on_ts = None

    # If still on at end of window, count until now
    if prev_on_ts is not None:
        _add_duration(result, prev_on_ts, datetime.now(timezone.utc),
                      power_kw, price_per_kwh, TZ_OFFSET)

    return result


def _add_duration(result, start_ts, end_ts, power_kw, price_per_kwh, tz_offset):
    """Split a [start, end) interval across calendar days and add energy."""
    cur = start_ts
    while cur < end_ts:
        # End of current local day
        local_cur   = cur + tz_offset
        day_str     = str(local_cur.date())
        next_midnight = (datetime(local_cur.year, local_cur.month, local_cur.day,
                                  tzinfo=timezone.utc) + timedelta(days=1)) - tz_offset
        seg_end = min(end_ts, next_midnight)
        hours   = (seg_end - cur).total_seconds() / 3600
        kwh     = hours * power_kw
        if day_str in result:
            result[day_str]["kwh"]        += kwh
            result[day_str]["cost_ils"]   += kwh * price_per_kwh
            result[day_str]["minutes_on"] += int(hours * 60)
        cur = seg_end


# ── STORAGE HELPERS ───────────────────────────────────────

def _parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def _extract_ts(item):
    """Extract ISO timestamp string from various Sensibo API response shapes."""
    t = item.get("time")
    if isinstance(t, dict):
        return t.get("time") or t.get("utc") or t.get("iso") or ""
    if isinstance(t, str):
        return t
    return item.get("ts") or item.get("timestamp") or item.get("createdAt") or ""

def _measurement_from_pod(pod):
    """Extract latest measurement dict from a pod object."""
    m = pod.get("measurements")
    if not m:
        return None
    # measurements is a dict with temperature, humidity, time{time, secondsAgo}
    temp = m.get("temperature")
    hum  = m.get("humidity")
    ts   = _extract_ts(m)
    if temp is None or not ts:
        return None
    return {
        "ts":          ts,
        "temperature": temp,
        "humidity":    hum,
        "feelsLike":   m.get("feelsLike"),
        "rssi":        m.get("rssi"),
    }

def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

def merge_measurements(existing, device_id, new_items):
    seen   = {r["ts"] for r in existing.get(device_id, [])}
    merged = list(existing.get(device_id, []))
    added  = 0
    for item in new_items:
        if item["ts"] not in seen:
            merged.append(item)
            seen.add(item["ts"])
            added += 1
    merged.sort(key=lambda x: x["ts"])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    merged = [r for r in merged if r["ts"] >= cutoff]
    print(f"  Measurements: +{added} new, {len(merged)} total kept.")
    return merged

def merge_energy(existing, device_id, new_daily):
    """Merge/overwrite daily energy records (always overwrite last 3 days)."""
    device_energy = existing.get(device_id, {})
    for day, vals in new_daily.items():
        device_energy[day] = {
            "kwh":        round(vals["kwh"],        3),
            "cost_ils":   round(vals["cost_ils"],   2),
            "minutes_on": vals["minutes_on"],
        }
    # Trim to 90 days
    cutoff = str((date.today() - timedelta(days=90)))
    device_energy = {k: v for k, v in device_energy.items() if k >= cutoff}
    print(f"  Energy: {len(device_energy)} days stored.")
    return device_energy


# ── MAIN ──────────────────────────────────────────────────

def main():
    if not API_KEY:
        raise EnvironmentError("SENSIBO_API_KEY secret is not set.")

    config        = load_config()
    price_per_kwh = float(config.get("price_per_kwh", 0.65))
    default_power = float(config.get("default_power_kw", 2.5))

    print(f"Fetching Sensibo data at {datetime.utcnow().isoformat()}Z")
    print(f"Config: default_power={default_power} kW, price={price_per_kwh} ₪/kWh")

    devices = get_devices()
    print(f"Found {len(devices)} device(s).")

    meas_data   = load_json(DATA_FILE)
    energy_data = load_json(ENERGY_FILE)

    for device in devices:
        device_id = device["id"]
        room      = device.get("room", {}).get("name", device_id)
        power_kw  = get_device_power(config, room)
        print(f"\nDevice: '{room}' ({device_id}) — {power_kw} kW")

        # Measurements
        new_meas = get_measurements(device_id, days_back=2)
        meas_data[device_id]                  = merge_measurements(meas_data, device_id, new_meas)
        meas_data[f"{device_id}__name"]       = room

        # Energy
        try:
            events    = get_ac_events(device_id, days_back=3)
            print(f"  AC events fetched: {len(events)}")
            daily_kwh = compute_daily_energy(events, power_kw, price_per_kwh, days_back=3)
            energy_data[device_id]            = merge_energy(energy_data, device_id, daily_kwh)
            energy_data[f"{device_id}__name"] = room
        except Exception as e:
            print(f"  ⚠ Could not fetch energy events: {e}")

    # Store config so dashboard can display units/power per device
    energy_data["__config"] = {
        "price_per_kwh":  price_per_kwh,
        "currency":       "₪",
        "device_power":   {room: get_device_power(config, room) for room in
                           [d.get("room", {}).get("name", d["id"]) for d in devices]},
    }

    save_json(DATA_FILE,   meas_data)
    save_json(ENERGY_FILE, energy_data)
    print("\nDone.")

if __name__ == "__main__":
    main()
