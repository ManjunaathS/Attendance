import { useEffect, useState } from "react";
import { Coffee } from "lucide-react";
import { get, post } from "../api";
import {
  Badge,
  Button,
  Empty,
  Heading,
  Modal,
  Panel,
  SectionHead,
  Stat,
  fmtDate,
  mins,
  todayISO,
  monthISO,
} from "../ui";
import useResource from "../useResource";
import { AttendanceCard, LocationLink, PeopleTable } from "./shared";
export default function Attendance({
  account,
  role,
  refresh,
  refreshAll,
  notify,
  onModal,
}) {
  const [month, setMonth] = useState(monthISO()),
    [date, setDate] = useState(todayISO()),
    [query, setQuery] = useState(""),
    [form, setForm] = useState(false),
    [busy, setBusy] = useState(false),
    [fallback, setFallback] = useState(null);
  const { data: mine = [] } = useResource(
    `/attendance/me?month=${month}`,
    refresh,
    Boolean(account.employee_id),
  );
  const { data: team = [] } = useResource(
    `/attendance/team?work_date=${date}`,
    refresh,
    role !== "EMPLOYEE",
  );
  const { data: teamMonthly = [] } = useResource(
    `/attendance/team?month=${month}`,
    refresh,
    role !== "EMPLOYEE",
  );
  const { data: regs = [] } = useResource(
    "/attendance/regularizations",
    refresh,
  );
  const day = mine.find((d) => d.date === todayISO()),
    rows =
      role === "EMPLOYEE"
        ? mine
        : team.filter(
            (e) =>
              !query ||
              e.employee_name?.toLowerCase().includes(query.toLowerCase()),
          );
  const monthlyByEmployee = Object.values(
    teamMonthly.reduce((groups, row) => {
      const key = row.employee_id || row.employee_name;
      if (!groups[key])
        groups[key] = {
          id: key,
          name: row.employee_name || "Employee",
          days: 0,
          work: 0,
          break: 0,
        };
      groups[key].days += 1;
      groups[key].work += row.work_minutes || 0;
      groups[key].break += row.break_minutes || 0;
      return groups;
    }, {}),
  ).sort((a, b) => a.name.localeCompare(b.name));
  const hasLiveAttendance = [...mine, ...team].some(
    (d) =>
      d.punches?.some((p) => p.type === "CHECK_IN") &&
      !d.punches?.some((p) => p.type === "CHECK_OUT"),
  );
  useEffect(() => {
    if (!hasLiveAttendance) return;
    const timer = setInterval(() => refreshAll(), 30000);
    return () => clearInterval(timer);
  }, [hasLiveAttendance]);
  const [reg, setReg] = useState({
    work_date: todayISO(),
    time: "",
    reason: "",
  });
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await post("/attendance/regularizations", {
        work_date: reg.work_date,
        punch_type: "CHECK_OUT",
        corrected_at: new Date(`${reg.work_date}T${reg.time}:00`).toISOString(),
        reason: reg.reason,
      });
      setForm(false);
      refreshAll();
      notify(
        "Regularization submitted. Your next check-in is locked until the manager decides.",
      );
    } catch (err) {
      notify(err.message);
    } finally {
      setBusy(false);
    }
  }
  function decide(r, decision) {
    onModal({
      kind: "decision",
      decision,
      item: {
        ...r,
        type: "Missed punch",
        employee_name: r.employee_name || "Team member",
      },
      success: `Regularization ${decision.toLowerCase()}.`,
      action: () =>
        post(`/attendance/regularizations/${r.id}/decision`, { decision }),
    });
  }
  function locationText(d) {
    if (d.work_mode === "WFH") return "WFH · not collected";
    const checkIn = d.punches?.find((p) => p.type === "CHECK_IN"),
      checkOut = d.punches?.find((p) => p.type === "CHECK_OUT");
    return (
      <>
        {checkIn ? <LocationLink punch={checkIn} label="In" /> : "In: —"}
        <br />
        {checkOut ? <LocationLink punch={checkOut} label="Out" /> : "Out: —"}
      </>
    );
  }
  return (
    <>
      <Heading
        eyebrow={role === "EMPLOYEE" ? "YOUR RECORDS" : "PEOPLE OPERATIONS"}
        title={
          role === "MANAGER"
            ? "Team attendance"
            : role === "HR"
              ? "HR attendance"
              : role === "ADMIN"
                ? "Attendance administration"
                : "Attendance"
        }
        // description="Monthly punches, work time, break periods, and attendance history."
        actions={
          role === "EMPLOYEE" &&
          day?.status === "INCOMPLETE" && (
            <Button tone="primary" onClick={() => setForm(true)}>
              Regularize missed punch
            </Button>
          )
        }
      />
      {account.employee_id && (
        <AttendanceCard
          day={day}
          role={role}
          refreshAll={refreshAll}
          notify={notify}
        />
      )}
      {role === "EMPLOYEE" ? (
        <>
          <div className="stats-grid three">
            <Stat
              label="TOTAL WORKED"
              value={mins(mine.reduce((n, x) => n + x.work_minutes, 0))}
              note={month}
              icon={Coffee}
            />
            <Stat
              label="TOTAL BREAK"
              value={mins(mine.reduce((n, x) => n + x.break_minutes, 0))}
              note="1h daily allowance"
              icon={Coffee}
              tone="amber"
            />
            <Stat
              label="LATE ARRIVALS"
              value={mine.filter((x) => x.status === "LATE").length}
              note="This month"
              icon={Coffee}
            />
          </div>
          <Panel>
            <SectionHead title="Monthly attendance" subtitle={month} />
            <div className="month-control">
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
              />
              <Badge>{mine.length} recorded days</Badge>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>DATE</th>
                    <th>MODE</th>
                    <th>LOCATION STATUS</th>
                    <th>CHECK IN</th>
                    <th>CHECK OUT</th>
                    <th>WORKED</th>
                    <th>BREAK PERIODS</th>
                    <th>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {mine.map((d) => (
                    <tr key={d.id}>
                      <td>{fmtDate(d.date)}</td>
                      <td>{d.work_mode}</td>
                      <td>{locationText(d)}</td>
                      <td>
                        {d.punches.find((p) => p.type === "CHECK_IN")?.at
                          ? new Date(
                              d.punches.find((p) => p.type === "CHECK_IN").at,
                            ).toLocaleTimeString("en-IN", {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                      <td>
                        {d.punches.find((p) => p.type === "CHECK_OUT")?.at
                          ? new Date(
                              d.punches.find((p) => p.type === "CHECK_OUT").at,
                            ).toLocaleTimeString("en-IN", {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                      <td>{mins(d.work_minutes)}</td>
                      <td>
                        <b>{mins(d.break_minutes)}</b>
                        {d.breaks.map((b, i) => (
                          <small className="subline" key={b.id}>
                            Break {i + 1}: {b.start.slice(11, 16)} –{" "}
                            {b.end?.slice(11, 16) || "Active"}
                          </small>
                        ))}
                      </td>
                      <td>
                        <Badge
                          tone={
                            d.status === "PRESENT"
                              ? "green"
                              : d.status === "LATE"
                                ? "amber"
                                : d.status === "ABSENT"
                                  ? "red"
                                  : "gray"
                          }
                        >
                          {d.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!mine.length && (
                <Empty>No attendance records for this month.</Empty>
              )}
            </div>
          </Panel>
        </>
      ) : (
        <>
          <div className="stats-grid three">
            <Stat
              label="TOTAL WORKED"
              value={mins(teamMonthly.reduce((n, x) => n + x.work_minutes, 0))}
              note={`${month} · ${role === "MANAGER" ? "team" : "company"}`}
              icon={Coffee}
            />
            <Stat
              label="TOTAL BREAK"
              value={mins(teamMonthly.reduce((n, x) => n + x.break_minutes, 0))}
              note={`${teamMonthly.length} attendance records`}
              icon={Coffee}
              tone="amber"
            />
            <Stat
              label="AVERAGE WORKED"
              value={mins(
                teamMonthly.length
                  ? Math.round(
                      teamMonthly.reduce((n, x) => n + x.work_minutes, 0) /
                        teamMonthly.length,
                    )
                  : 0,
              )}
              note="Per recorded shift"
              icon={Coffee}
            />
          </div>
          <Panel>
            <SectionHead title="Monthly totals by employee" subtitle={month} />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>EMPLOYEE</th>
                    <th>WORKING DAYS</th>
                    <th>TOTAL WORKED</th>
                    <th>TOTAL BREAK</th>
                  </tr>
                </thead>
                <tbody>
                  {monthlyByEmployee.map((person) => (
                    <tr key={person.id}>
                      <td>{person.name}</td>
                      <td>{person.days}</td>
                      <td>{mins(person.work)}</td>
                      <td>{mins(person.break)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!monthlyByEmployee.length && (
                <Empty>No attendance totals for this month.</Empty>
              )}
            </div>
          </Panel>
          <Panel>
            <SectionHead
              title={
                role === "MANAGER"
                  ? "My team records"
                  : "Company attendance records"
              }
              subtitle={
                role === "MANAGER"
                  ? "Team scope · current members"
                  : "HR/Admin company-wide scope"
              }
            />
            <div className="filters">
              <input
                className="control"
                placeholder="Search employees"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <label className="date-filter">
                Date
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
            </div>
            <PeopleTable rows={rows} />
          </Panel>
        </>
      )}
      {regs.length > 0 && (
        <Panel>
          <SectionHead
            title="Missed-punch regularizations"
            subtitle="Review corrections for your scope"
          />
          {regs.map((r) => (
            <div className="request-row" key={r.id}>
              <div className="request-info">
                <b>{r.employee_name || "Regularization request"}</b>
                <small>
                  {r.corrected_at} · {r.reason}
                </small>
                {r.fallback_reason && (
                  <small className="fallback-note">
                    HR fallback · {r.fallback_reason}
                  </small>
                )}
              </div>
              <Badge
                tone={
                  r.status === "APPROVED"
                    ? "green"
                    : r.status === "REJECTED"
                      ? "red"
                      : "amber"
                }
              >
                {r.status}
              </Badge>
              {r.status === "PENDING_MANAGER" &&
                ((role === "MANAGER" && r.manager_id === account.id) ||
                  role === "ADMIN" ||
                  (role === "HR" && r.fallback_reason)) && (
                  <div className="button-pair">
                    <Button
                      tone="approve"
                      onClick={() => decide(r, "APPROVED")}
                    >
                      Approve
                    </Button>
                    <Button tone="reject" onClick={() => decide(r, "REJECTED")}>
                      Reject
                    </Button>
                  </div>
                )}
              {r.status === "PENDING_MANAGER" &&
                role === "HR" &&
                !r.fallback_reason && (
                  <Button onClick={() => setFallback(r)}>Delegate to HR</Button>
                )}
            </div>
          ))}
        </Panel>
      )}
      {form && (
        <Modal
          title="Regularize missed punch"
          description="Enter the missing check-out time and reason. Your next check-in remains locked until approval."
          onClose={() => setForm(false)}
        >
          <form className="form" onSubmit={submit}>
            <label>
              Work date
              <input
                type="date"
                value={reg.work_date}
                onChange={(e) => setReg({ ...reg, work_date: e.target.value })}
                required
              />
            </label>
            <label>
              Correct check-out time
              <input
                type="time"
                value={reg.time}
                onChange={(e) => setReg({ ...reg, time: e.target.value })}
                required
              />
            </label>
            <label>
              Reason
              <textarea
                value={reg.reason}
                onChange={(e) => setReg({ ...reg, reason: e.target.value })}
                minLength={5}
                required
              />
            </label>
            <div className="modal-actions">
              <Button onClick={() => setForm(false)}>Cancel</Button>
              <Button type="submit" tone="primary" disabled={busy}>
                Submit for approval
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {fallback && (
        <Modal
          title="Delegate missed-punch review"
          description={fallback.employee_name}
          onClose={() => setFallback(null)}
        >
          <form
            className="form"
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              try {
                await post(
                  `/attendance/regularizations/${fallback.id}/delegate-to-hr`,
                  { reason: data.get("reason") },
                );
                setFallback(null);
                refreshAll();
                notify("Regularization delegated to HR.");
              } catch (err) {
                notify(err.message);
              }
            }}
          >
            <label>
              Fallback reason
              <textarea
                name="reason"
                minLength={5}
                required
                placeholder="Manager is on leave / unavailable…"
              />
            </label>
            <div className="modal-actions">
              <Button onClick={() => setFallback(null)}>Cancel</Button>
              <Button tone="primary" type="submit">
                Delegate to HR
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
