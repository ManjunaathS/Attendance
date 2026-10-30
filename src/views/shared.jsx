import { useEffect, useState } from "react";
import { Check, Coffee, ListTodo, MapPin } from "lucide-react";
import { get, post } from "../api";
import {
  Badge,
  Button,
  Empty,
  Panel,
  SectionHead,
  todayISO,
  fmtDate,
  mins,
} from "../ui";

const punchTime = (punch) =>
  punch?.at
    ? new Date(punch.at).toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

export function LocationLink({ punch, label }) {
  if (punch?.latitude == null || punch?.longitude == null)
    return <span>{label} location not recorded</span>;
  const coordinates = `${punch.latitude},${punch.longitude}`;
  return (
    <a
      className="map-link"
      href={`https://www.google.com/maps?q=${encodeURIComponent(coordinates)}`}
      target="_blank"
      rel="noopener noreferrer"
      title={`Open ${label.toLowerCase()} location in Google Maps · ${coordinates}`}
      aria-label={`Open ${label.toLowerCase()} location in Google Maps`}
    >
      <MapPin size={14} />
      <span>
        {label} · ±{Math.round(punch.accuracy_meters || 0)}m
      </span>
    </a>
  );
}

export function AttendanceCard({ day, role, refreshAll, notify }) {
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const [shift, setShift] = useState("SHIFT_1");
  const [mode, setMode] = useState("OFFICE");
  const [busy, setBusy] = useState(false);
  const [breaks, setBreaks] = useState([]);
  const [locationPermission, setLocationPermission] = useState("checking");

  useEffect(() => {
    if (role === "ADMIN") return;
    get("/attendance/config")
      .then((c) => {
        setConfig(c);
        setConfigError("");
        setShift(c.shifts?.[0]?.code || "SHIFT_1");
        if (c.wfh_approved_today) setMode("WFH");
      })
      .catch((e) => {
        setConfigError(e.message);
        notify(e.message);
      });
  }, [role]);

  useEffect(() => setBreaks(day?.breaks || []), [day]);
  useEffect(() => {
    if (!navigator.geolocation) {
      setLocationPermission("unsupported");
      return;
    }
    if (!navigator.permissions?.query) {
      setLocationPermission("prompt");
      return;
    }
    let permission;
    navigator.permissions
      .query({ name: "geolocation" })
      .then((p) => {
        permission = p;
        setLocationPermission(p.state);
        p.onchange = () => setLocationPermission(p.state);
      })
      .catch(() => setLocationPermission("prompt"));
    return () => {
      if (permission) permission.onchange = null;
    };
  }, []);

  const openBreak = breaks.find((b) => !b.end);
  const checkedOut = day?.punches?.some((p) => p.type === "CHECK_OUT");
  const checkedIn = day && !checkedOut && day.status !== "ABSENT";
  const officePunch = day?.punches?.find(
    (p) => p.type === "CHECK_IN" && p.latitude != null,
  );
  const status = day?.status || "NOT_STARTED";

  async function punchIn() {
    setBusy(true);
    try {
      let loc = {};
      if (mode === "OFFICE") {
        if (!navigator.geolocation)
          throw Error(
            "This browser cannot provide precise location. Office attendance is blocked.",
          );
        loc = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(
            (p) =>
              resolve({
                latitude: p.coords.latitude,
                longitude: p.coords.longitude,
                accuracy_meters: p.coords.accuracy,
              }),
            () => {
              setLocationPermission("denied");
              reject(
                Error(
                  "Location access was denied. Allow precise location to check in at the office.",
                ),
              );
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
          ),
        );
        setLocationPermission("granted");
        if (
          loc.accuracy_meters >
          (config?.office_location_accuracy_limit_meters || 50)
        )
          throw Error(
            "Location accuracy must be 50 meters or better. Enable precise location and retry.",
          );
      }
      await post("/attendance/check-in", {
        work_mode: mode,
        shift_code: shift,
        ...loc,
      });
      notify(`${mode === "OFFICE" ? "Office" : "WFH"} check-in recorded.`);
      refreshAll();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function punchOut() {
    setBusy(true);
    try {
      let loc = {};
      if (day.work_mode === "OFFICE") {
        if (!navigator.geolocation)
          throw Error(
            "This browser cannot provide precise location. Office attendance is blocked.",
          );
        loc = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(
            (p) =>
              resolve({
                latitude: p.coords.latitude,
                longitude: p.coords.longitude,
                accuracy_meters: p.coords.accuracy,
              }),
            () => {
              setLocationPermission("denied");
              reject(
                Error(
                  "Precise location is required to check out from the office.",
                ),
              );
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
          ),
        );
        setLocationPermission("granted");
        if (
          loc.accuracy_meters >
          (config?.office_location_accuracy_limit_meters || 50)
        )
          throw Error(
            "Location accuracy must be 50 meters or better. Enable precise location and retry.",
          );
      }
      await post("/attendance/check-out", loc);
      notify("Check-out recorded.");
      refreshAll();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleBreak() {
    try {
      if (openBreak) {
        const result = await post(`/attendance/breaks/${openBreak.id}/end`, {});
        notify(
          `Break out recorded. Total ${mins(result.total_break_minutes)}${result.hr_review_required ? " · HR review needed" : ""}.`,
        );
      } else {
        await post("/attendance/breaks/start", {});
        notify("Break in recorded.");
      }
      refreshAll();
    } catch (e) {
      notify(e.message);
    }
  }

  const permissionLabel =
    locationPermission === "granted"
      ? "Permission granted"
      : locationPermission === "denied"
        ? "Permission denied"
        : locationPermission === "unsupported"
          ? "Location unavailable"
          : `Permission: ${locationPermission}`;

  return (
    <Panel className="live-card">
      <div className="live-top">
        <div>
          <span className="muted">
            TODAY ·{" "}
            {fmtDate(todayISO(), {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </span>
          <h2>
            {status === "ABSENT"
              ? "Marked absent"
              : checkedOut
                ? "Day complete"
                : openBreak
                  ? "You’re on break"
                  : checkedIn
                    ? "You’re checked in"
                    : "Ready to check in"}
          </h2>
          <p>
            {day
              ? `${day.work_mode} · ${shift}`
              : (config?.shifts || [])
                  .map(
                    (s) =>
                      `${s.name} ${s.start.slice(0, 5)}–${s.end.slice(0, 5)}`,
                  )
                  .join(" · ")}
          </p>
        </div>
        <Badge
          tone={status === "LATE" ? "amber" : checkedIn ? "green" : "gray"}
        >
          {status === "NOT_STARTED" ? "NOT CHECKED IN" : status}
        </Badge>
      </div>

      {day?.work_mode === "OFFICE" && (
        <div className="punch-locations">
          <div className="location-note">
            <LocationLink punch={officePunch} label="Check-in" />
          </div>
          {day.punches?.some((p) => p.type === "CHECK_OUT") &&
            (() => {
              const out = day.punches.find((p) => p.type === "CHECK_OUT");
              return (
                <div className="location-note">
                  <LocationLink punch={out} label="Check-out" />
                </div>
              );
            })()}
        </div>
      )}
      {!day && !config && (
        <div className="notice-box">
          {configError
            ? `Check-in setup unavailable: ${configError}`
            : "Loading shift and work-mode options…"}
        </div>
      )}

      {!day && config && (
        <div className="attendance-tools">
          <label>
            Shift
            <select
              className="control"
              value={shift}
              disabled={config.shift_mode === "MANAGER_ASSIGNED"}
              onChange={(e) => setShift(e.target.value)}
            >
              {config.shifts.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name} · {s.start.slice(0, 5)}–{s.end.slice(0, 5)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Work mode
            <select
              className="control"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="OFFICE">Office</option>
              <option value="WFH" disabled={!config.wfh_approved_today}>
                WFH
                {config.wfh_approved_today
                  ? " · approved"
                  : " · approval required"}
              </option>
            </select>
          </label>
          <Button tone="primary" disabled={busy} onClick={punchIn}>
            {busy ? "Checking location…" : "Check in"}
          </Button>
          <span className="location-note">
            {mode === "OFFICE" ? (
              <>
                <MapPin size={14} /> {permissionLabel} · accuracy must be ≤
                {config.office_location_accuracy_limit_meters}m
              </>
            ) : (
              "Approved WFH · no location requested"
            )}
          </span>
          {!config.wfh_approved_today && (
            <small className="location-note">
              Request WFH in Leave, permission &amp; WFH; it appears here after
              manager approval.
            </small>
          )}
        </div>
      )}

      {checkedIn && !checkedOut && (
        <div className="attendance-tools">
          <Button onClick={toggleBreak}>
            {openBreak ? (
              <>
                <Check size={15} /> Break out
              </>
            ) : (
              <>
                <Coffee size={15} /> Break in
              </>
            )}
          </Button>
          <Button
            tone="primary"
            onClick={punchOut}
            disabled={busy || Boolean(openBreak)}
          >
            Check out
          </Button>
          {openBreak && (
            <span className="location-note">
              End your active break before checking out.
            </span>
          )}
        </div>
      )}

      <div className="live-stats">
        <span>
          <small>WORKED</small>
          <b>{mins(day?.work_minutes)}</b>
        </span>
        <span>
          <small>TOTAL BREAK</small>
          <b>
            {mins(day?.break_minutes)} <i>/ 1h</i>
          </b>
        </span>
        <span>
          <small>BREAK PERIODS</small>
          <b>{breaks.length} recorded</b>
        </span>
      </div>
      <div className="progress">
        <i
          style={{
            width: `${Math.min(100, ((day?.work_minutes || 0) / 480) * 100)}%`,
          }}
        />
      </div>
    </Panel>
  );
}

function locationStatus(row) {
  if (row.work_mode === "WFH") return "WFH · location not requested";
  const format = (type) => {
    const punch = row.punches?.find((p) => p.type === type);
    if (!punch) return null;
    return punch.latitude == null ? (
      `${type === "CHECK_IN" ? "In" : "Out"}: not recorded`
    ) : (
      <LocationLink
        punch={punch}
        label={type === "CHECK_IN" ? "Check-in" : "Check-out"}
      />
    );
  };
  return (
    <>
      {format("CHECK_IN") || "In: —"}
      <br />
      {format("CHECK_OUT") || "Out: —"}
    </>
  );
}

export function PeopleTable({ rows = [] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>EMPLOYEE</th>
            <th>CHECK IN</th>
            <th>CHECK OUT</th>
            <th>LOCATION STATUS · IN / OUT</th>
            <th>WORKED</th>
            <th>BREAK</th>
            <th>STATUS</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <div className="person">
                  <span className="avatar">
                    {(r.employee_name || "?")
                      .split(" ")
                      .map((x) => x[0])
                      .join("")
                      .slice(0, 2)}
                  </span>
                  <span>
                    <b>{r.employee_name || "Employee"}</b>
                    <small>{r.team_name || ""}</small>
                  </span>
                </div>
              </td>
              <td>
                {punchTime(r.punches?.find((p) => p.type === "CHECK_IN"))}
              </td>
              <td>
                {punchTime(r.punches?.find((p) => p.type === "CHECK_OUT"))}
              </td>
              <td>{locationStatus(r)}</td>
              <td>{mins(r.work_minutes)}</td>
              <td>{mins(r.break_minutes)}</td>
              <td>
                <Badge
                  tone={
                    r.status === "PRESENT"
                      ? "green"
                      : r.status === "LATE"
                        ? "amber"
                        : r.status === "ABSENT"
                          ? "red"
                          : "gray"
                  }
                >
                  {r.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <Empty>No attendance records for this date.</Empty>}
    </div>
  );
}

export function TaskRow({ task }) {
  return (
    <div className="task-row">
      <span className="request-icon">
        <ListTodo size={16} />
      </span>
      <div className="request-info">
        <b>{task.title}</b>
        <small>
          Assigned to {task.assignee || "Unknown employee"} · Assigned by{" "}
          {task.assigner || "Unknown"}
        </small>
        <small>
          Due {task.due_date || "No due date"} · Priority {task.priority}
        </small>
        {task.description && <small>{task.description}</small>}
        {task.status === "PENDING" && (
          <small>Waiting: {task.pending_reason}</small>
        )}
      </div>
      <Badge
        tone={
          task.status === "COMPLETED"
            ? "green"
            : task.status === "IN_PROGRESS"
              ? "purple"
              : task.status === "PENDING"
                ? "amber"
                : "gray"
        }
      >
        {task.status.replace("_", " ")}
      </Badge>
    </div>
  );
}

export function RequestDecision({ item, account, role, onModal, endpoint }) {
  const allowed =
    role === "ADMIN" ||
    (role === "MANAGER" &&
      item.status === "PENDING_MANAGER" &&
      item.manager_id === account.id) ||
    (role === "HR" &&
      item.status === "PENDING_MANAGER" &&
      item.manager_unavailable);
  if (!allowed) return null;
  const ask = (decision) =>
    onModal({
      kind: "decision",
      decision,
      item,
      success: `${item.type || "Request"} ${decision.toLowerCase()}.`,
      action: () => post(endpoint, { decision }),
    });
  return (
    <div className="button-pair">
      <Button tone="approve" onClick={() => ask("APPROVED")}>
        Approve
      </Button>
      <Button tone="reject" onClick={() => ask("REJECTED")}>
        Reject
      </Button>
    </div>
  );
}
