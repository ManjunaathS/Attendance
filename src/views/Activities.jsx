import { useEffect, useState } from "react";
import { ClipboardList, Eye, MessageSquareText, Plus } from "lucide-react";
import { get, patch, post } from "../api";
import {
  Badge,
  Button,
  Empty,
  Heading,
  Modal,
  Notice,
  Panel,
  SectionHead,
  todayISO,
  monthISO,
  fmtDate,
} from "../ui";
import useResource from "../useResource";

export default function Activities({
  account,
  role,
  refresh,
  refreshAll,
  notify,
}) {
  const [month, setMonth] = useState(monthISO());
  const [showForm, setShowForm] = useState(false);
  const [view, setView] = useState(null);
  const [remarkRow, setRemarkRow] = useState(null);
  const [remark, setRemark] = useState("");
  const [date, setDate] = useState(todayISO());
  const [shiftCode, setShiftCode] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [description, setDescription] = useState("");
  const [shifts, setShifts] = useState([]);
  const [loadingShifts, setLoadingShifts] = useState(false);
  const [saving, setSaving] = useState(false);
  const { data: rows = [] } = useResource(
    `/activities?month=${month}`,
    refresh,
  );
  const canCreate = Boolean(account.employee_id);
  const canRemark = role === "MANAGER" || role === "ADMIN";

  async function loadShifts(forDate) {
    setLoadingShifts(true);
    try {
      const config = await get(`/activities/config?activity_date=${forDate}`);
      setShifts(config.shifts || []);
      const selected =
        (config.shifts || []).find((s) => s.code === shiftCode) ||
        (config.shifts || [])[0];
      setShiftCode(selected?.code || "");
      setStartTime(selected?.start || "");
      setEndTime(selected?.end || "");
    } catch (error) {
      setShifts([]);
      notify(error.message);
    } finally {
      setLoadingShifts(false);
    }
  }
  useEffect(() => {
    if (showForm) loadShifts(date);
  }, [showForm]);

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const created = await post("/activities", {
        activity_date: date,
        shift_code: shiftCode,
        start_time: startTime,
        end_time: endTime,
        description: description.trim(),
      });
      setShowForm(false);
      setDescription("");
      refreshAll();
      setView(created);
      notify("Daily activity submitted.");
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  }
  async function saveRemark(e) {
    e.preventDefault();
    if (!remarkRow) return;
    setSaving(true);
    try {
      await patch(`/activities/${remarkRow.id}/remark`, {
        remark: remark.trim(),
      });
      setRemarkRow(null);
      refreshAll();
      notify("Manager remark saved.");
    } catch (error) {
      notify(error.message);
    } finally {
      setSaving(false);
    }
  }
  const openForm = () => {
    setDate(todayISO());
    setShiftCode("");
    setStartTime("");
    setEndTime("");
    setDescription("");
    setShowForm(true);
  };

  return (
    <>
      <Heading
        title="Activity sheet"
        description={
          role === "EMPLOYEE"
            ? "Record and review your daily work activities."
            : role === "MANAGER"
              ? "Review your team’s daily activities and add manager remarks."
              : "Monitor company daily activity records."
        }
        actions={
          canCreate && (
            <Button tone="primary" onClick={openForm}>
              <Plus size={15} /> Add Daily Activity
            </Button>
          )
        }
      />
      <Panel>
        <SectionHead
          title={
            role === "EMPLOYEE"
              ? "My daily activities"
              : role === "MANAGER"
                ? "Team activity records"
                : "Company activity records"
          }
          subtitle={`${rows.length} entries · ${role === "MANAGER" ? "assigned team scope" : role === "EMPLOYEE" ? "your records" : "company-wide visibility"}`}
          action={
            <label className="month-control">
              Month {" "}
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
              />
            </label>
          }
        />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>DATE</th>
                {role !== "EMPLOYEE" && <th>EMPLOYEE</th>}
                <th>SHIFT</th>
                <th>TIME</th>
                <th>DESCRIPTION</th>
                <th>MANAGER REMARK</th>
                <th>VIEW</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{fmtDate(row.activity_date)}</td>
                  {role !== "EMPLOYEE" && (
                    <td>
                      <b>{row.employee_name}</b>
                      <small className="subline">{row.team_name}</small>
                    </td>
                  )}
                  <td>{row.shift_name}</td>
                  <td>
                    {row.start_time}–{row.end_time}
                    <small className="subline">
                      {row.shift_start}–{row.shift_end}
                    </small>
                  </td>
                  <td className="activity-description">{row.description}</td>
                  <td>
                    {row.manager_remark ? (
                      <>
                        <span>{row.manager_remark}</span>
                        {row.remarked_by && (
                          <small className="subline">
                            By {row.remarked_by}
                          </small>
                        )}
                      </>
                    ) : (
                      <span className="muted">No remark</span>
                    )}
                  </td>
                  <td>
                    <div className="activity-actions">
                      <Button
                        className="icon-action"
                        title="View activity"
                        onClick={() => setView(row)}
                      >
                        <Eye size={15} />
                      </Button>
                      {canRemark &&
                        (role === "ADMIN" ||
                          (role === "MANAGER" &&
                            row.manager_id === account.id)) && (
                          <Button
                            title="Add manager remark"
                            onClick={() => {
                              setRemarkRow(row);
                              setRemark(row.manager_remark || "");
                            }}
                          >
                            <MessageSquareText size={14} />
                            {row.manager_remark ? "Edit remark" : "Add remark"}
                          </Button>
                        )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty>No activity records for this month.</Empty>}
        </div>
      </Panel>

      {showForm && (
        <Modal
          title="Add daily activity"
          description="Enter an activity within your shift hours. You can add multiple non-overlapping entries for a day."
          onClose={() => setShowForm(false)}
        >
          <form className="form" onSubmit={submit}>
            <label>
              Activity date
              <input
                type="date"
                max={todayISO()}
                value={date}
                onChange={(e) => {
                  setDate(e.target.value);
                  loadShifts(e.target.value);
                }}
                required
              />
            </label>
            {loadingShifts ? (
              <Notice>Loading shift timings…</Notice>
            ) : shifts.length ? (
              <>
                <label>
                  Shift
                  <select
                    value={shiftCode}
                    onChange={(e) => {
                      const selected = shifts.find(
                        (s) => s.code === e.target.value,
                      );
                      setShiftCode(e.target.value);
                      setStartTime(selected?.start || "");
                      setEndTime(selected?.end || "");
                    }}
                    required
                  >
                    {shifts.map((s) => (
                      <option key={s.id} value={s.code}>
                        {s.name} · {s.start}–{s.end}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="form-row">
                  <label>
                    Start time
                    <input
                      type="time"
                      min={shifts.find((s) => s.code === shiftCode)?.start}
                      max={shifts.find((s) => s.code === shiftCode)?.end}
                      value={startTime}
                      onChange={(e) => setStartTime(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    End time
                    <input
                      type="time"
                      min={shifts.find((s) => s.code === shiftCode)?.start}
                      max={shifts.find((s) => s.code === shiftCode)?.end}
                      value={endTime}
                      onChange={(e) => setEndTime(e.target.value)}
                      required
                    />
                  </label>
                </div>
                <Notice>
                  Shift hours: {shifts.find((s) => s.code === shiftCode)?.start}
                  –{shifts.find((s) => s.code === shiftCode)?.end}. Activity
                  times must stay within this window.
                </Notice>
              </>
            ) : (
              <Notice>
                No shift is available for this date. If your team uses
                manager-assigned shifts, ask your manager to assign one.
              </Notice>
            )}
            <label>
              Activity description
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                minLength={3}
                maxLength={4000}
                placeholder="Describe the work completed or in progress"
                required
              />
            </label>
            <div className="modal-actions">
              <Button onClick={() => setShowForm(false)}>Cancel</Button>
              <Button
                type="submit"
                tone="primary"
                disabled={saving || !shiftCode}
              >
                {saving ? "Saving…" : "Submit activity"}
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {view && (
        <Modal
          title="Activity details"
          description={`${view.employee_name || "Your activity"} · ${fmtDate(view.activity_date)}`}
          onClose={() => setView(null)}
        >
          <div className="activity-detail">
            <div>
              <small>SHIFT</small>
              <b>
                {view.shift_name} · {view.shift_start}–{view.shift_end}
              </b>
            </div>
            <div>
              <small>ACTIVITY TIME</small>
              <b>
                {view.start_time}–{view.end_time}
              </b>
            </div>
            <div>
              <small>DESCRIPTION</small>
              <p>{view.description}</p>
            </div>
            <div>
              <small>MANAGER REMARK</small>
              <p>{view.manager_remark || "No remark added yet."}</p>
              {view.remarked_by && <small>By {view.remarked_by}</small>}
            </div>
          </div>
          <div className="modal-actions">
            <Button onClick={() => setView(null)}>Close</Button>
          </div>
        </Modal>
      )}

      {remarkRow && (
        <Modal
          title="Manager remark"
          description={`${remarkRow.employee_name} · ${fmtDate(remarkRow.activity_date)} · ${remarkRow.start_time}–${remarkRow.end_time}`}
          onClose={() => setRemarkRow(null)}
        >
          <form className="form" onSubmit={saveRemark}>
            <label>
              Remark
              <textarea
                value={remark}
                onChange={(e) => setRemark(e.target.value)}
                minLength={1}
                maxLength={4000}
                required
                placeholder="Add feedback or a review note for this activity"
              />
            </label>
            <div className="modal-actions">
              <Button onClick={() => setRemarkRow(null)}>Cancel</Button>
              <Button type="submit" tone="primary" disabled={saving}>
                Save remark
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
