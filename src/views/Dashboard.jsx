import { useEffect, useState } from "react";
import {
  CalendarDays,
  Check,
  Clock3,
  Users,
  BriefcaseBusiness,
  Plus,
} from "lucide-react";
import { get, post } from "../api";
import {
  Badge,
  Button,
  Empty,
  Heading,
  Panel,
  SectionHead,
  Stat,
  fmtDate,
  mins,
} from "../ui";
import useResource from "../useResource";
import {
  AttendanceCard,
  PeopleTable,
  RequestDecision,
  TaskRow,
} from "./shared";

export default function Dashboard({
  account,
  role,
  refresh,
  refreshAll,
  notify,
  onPage,
  onModal,
}) {
  const [att, setAtt] = useState([]);
  const [team, setTeam] = useState([]);

  useEffect(() => {
    if (account.employee_id) {
      get(`/attendance/me?month=${new Date().toISOString().slice(0, 7)}`)
        .then((value) => setAtt(Array.isArray(value) ? value : []))
        .catch(() => {});
    }
    if (role !== "EMPLOYEE") {
      get(`/attendance/team?work_date=${new Date().toISOString().slice(0, 10)}`)
        .then((value) => setTeam(Array.isArray(value) ? value : []))
        .catch(() => {});
    }
  }, [account.employee_id, role, refresh]);

  const { data: balance } = useResource(
    "/time-off/balances/me",
    refresh,
    Boolean(account.employee_id),
  );
  const { data: tasks } = useResource("/tasks", refresh);
  const { data: reqs } = useResource(
    "/time-off/requests?status=PENDING_MANAGER",
    refresh,
    role !== "EMPLOYEE",
  );
  const { data: events } = useResource("/events", refresh);
  const { data: news } = useResource("/news", refresh);
  const { data: people } = useResource(
    "/employees",
    refresh,
    role !== "EMPLOYEE",
  );

  const taskRows = Array.isArray(tasks) ? tasks : [];
  const requestRows = Array.isArray(reqs) ? reqs : [];
  const eventRows = Array.isArray(events) ? events : [];
  const newsRows = Array.isArray(news) ? news : [];
  const employeeRows = Array.isArray(people)
    ? people.filter((person) => person.status === "ACTIVE")
    : [];
  const today = att.find(
    (day) => day.date === new Date().toISOString().slice(0, 10),
  );
  const name = account.display_name?.split(" ")[0] || "there";
  const present = team.filter((row) =>
    ["PRESENT", "LATE"].includes(row.status),
  ).length;
  const headcount =
    role === "EMPLOYEE" ? team.length : employeeRows.length || team.length;
  const hasLiveAttendance = [...att, ...team].some(
    (day) =>
      day.punches?.some((punch) => punch.type === "CHECK_IN") &&
      !day.punches?.some((punch) => punch.type === "CHECK_OUT"),
  );

  useEffect(() => {
    if (!hasLiveAttendance) return;
    const timer = setInterval(() => refreshAll(), 30000);
    return () => clearInterval(timer);
  }, [hasLiveAttendance]);

  const reloadRequest = (request, decision) =>
    onModal({
      kind: "decision",
      decision,
      item: request,
      success: `${request.type} ${decision.toLowerCase()}.`,
      action: () =>
        post(`/time-off/requests/${request.id}/decision`, { decision }),
    });

  return (
    <>
      <Heading
        eyebrow={role === "EMPLOYEE" ? "YOUR WORKSPACE" : "PEOPLE OPERATIONS"}
        title={`Good morning, ${name}`}
        description={`${new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date())} `}
        actions={
          role === "MANAGER" && (
            <Button tone="primary" onClick={() => onPage("tasks")}>
              <Plus size={15} /> Assign a task
            </Button>
          )
        }
      />

      <div className={`stats-grid ${role.toLowerCase()}-stats`}>
        {role === "EMPLOYEE" ? (
          <>
            <Stat
              label="WORKING DAYS"
              value={att.filter((day) => day.status !== "ABSENT").length}
              note="This month"
              icon={CalendarDays}
            />
            <Stat
              label="CASUAL LEAVE"
              value={`${balance?.casual_leave_days ?? "—"} days`}
              note="Available balance"
              icon={CalendarDays}
              tone="green"
            />
            <Stat
              label="SICK LEAVE"
              value={`${balance?.sick_leave_days ?? "—"} days`}
              note="Available balance"
              icon={Check}
              tone="amber"
            />
            <Stat
              label="PERMISSION LEFT"
              value={mins(balance?.permission_minutes_remaining)}
              note="Of 2h monthly allowance"
              icon={Clock3}
            />
          </>
        ) : (
          <>
            <Stat
              label="PRESENT TODAY"
              value={`${present} / ${headcount}`}
              note={role === "MANAGER" ? "Your team" : "Company attendance"}
              icon={Users}
              tone="green"
            />
            <Stat
              label="PENDING APPROVALS"
              value={requestRows.length}
              note="Time away requests"
              icon={Check}
              tone="amber"
            />
            <Stat
              label="TASKS IN PROGRESS"
              value={
                taskRows.filter((row) => row.status === "IN_PROGRESS").length
              }
              note="Assigned work"
              icon={BriefcaseBusiness}
            />
            <Stat
              label="ATTENDANCE EXCEPTIONS"
              value={
                team.filter(
                  (row) => row.break_minutes > 60 || row.status === "LATE",
                ).length
              }
              note="Late or excess break"
              icon={Clock3}
              tone="amber"
            />
          </>
        )}
      </div>

      <div className={`dashboard-grid ${role.toLowerCase()}-dashboard-grid`}>
        <div className="stack">
          {role !== "ADMIN" && account.employee_id && (
            <AttendanceCard
              day={today}
              role={role}
              refreshAll={refreshAll}
              notify={notify}
            />
          )}
          {role !== "EMPLOYEE" && (
            <Panel>
              <SectionHead
                title={
                  role === "MANAGER"
                    ? "My team attendance"
                    : "Company attendance"
                }
                subtitle={
                  role === "MANAGER" ? "Team records only" : "Company-wide view"
                }
                action={
                  <Button onClick={() => onPage("attendance")}>
                    View attendance
                  </Button>
                }
              />
              <PeopleTable rows={team.slice(0, 6)} />
            </Panel>
          )}
          {role === "EMPLOYEE" ? (
            <Panel>
              <SectionHead
                title="My tasks"
                subtitle="Your assigned work"
                action={
                  <Button onClick={() => onPage("tasks")}>View tasks</Button>
                }
              />
              {taskRows.slice(0, 4).map((task) => (
                <TaskRow task={task} key={task.id} />
              ))}
              {!taskRows.length && <Empty>No tasks assigned yet.</Empty>}
            </Panel>
          ) : (
            <Panel>
              <SectionHead
                title="Pending requests"
                subtitle="Review team requests"
                action={
                  <Button onClick={() => onPage("leave")}>
                    Open approvals
                  </Button>
                }
              />
              {requestRows.slice(0, 5).map((request) => (
                <div className="request-row" key={request.id}>
                  <span className="request-icon">
                    <CalendarDays size={16} />
                  </span>
                  <div className="request-info">
                    <b>
                      {request.type} · {request.employee_name}
                    </b>
                    <small>
                      {fmtDate(request.start_date)}
                      {request.end_date !== request.start_date
                        ? ` – ${fmtDate(request.end_date)}`
                        : ""}{" "}
                      · {request.reason}
                    </small>
                  </div>
                  <Badge tone="amber">Pending</Badge>
                  <RequestDecision
                    item={request}
                    account={account}
                    role={role}
                    onModal={onModal}
                    endpoint={`/time-off/requests/${request.id}/decision`}
                  />
                </div>
              ))}
              {!requestRows.length && (
                <Empty>No requests are awaiting review.</Empty>
              )}
            </Panel>
          )}
        </div>

        <aside className="stack">
          {balance && (
            <Panel className="balance-panel">
              <div className="eyebrow">MY LEAVE BALANCE</div>
              <strong>
                {(
                  (balance.casual_leave_days || 0) +
                  (balance.sick_leave_days || 0)
                ).toFixed(1)}{" "}
                <small>days available</small>
              </strong>
              <div className="balance-split">
                <span>
                  CASUAL LEAVE<b>{balance.casual_leave_days} days</b>
                </span>
                <span>
                  SICK LEAVE<b>{balance.sick_leave_days} days</b>
                </span>
              </div>
              <Button onClick={() => onPage("leave")}>View leave</Button>
            </Panel>
          )}
          <Panel>
            <SectionHead
              title="Upcoming events"
              action={<Button onClick={() => onPage("news")}>See all</Button>}
            />
            {eventRows.slice(0, 3).map((event) => (
              <div className="event-row" key={event.id}>
                <span className="event-date">
                  {fmtDate(event.starts_at, { day: "numeric", month: "short" })}
                </span>
                <div>
                  <b>{event.title}</b>
                  <small>{event.location || "Company event"}</small>
                </div>
              </div>
            ))}
            {!eventRows.length && <Empty>No published events yet.</Empty>}
          </Panel>
          <Panel>
            <SectionHead
              title="Latest news"
              action={<Button onClick={() => onPage("news")}>Read news</Button>}
            />
            {newsRows.slice(0, 3).map((item) => (
              <div className="news-row" key={item.id}>
                <span className="mini-symbol">✳</span>
                <div>
                  <b>{item.title}</b>
                  <small>{fmtDate(item.published_at)}</small>
                </div>
              </div>
            ))}
            {!newsRows.length && <Empty>No published updates yet.</Empty>}
          </Panel>
        </aside>
      </div>
    </>
  );
}
