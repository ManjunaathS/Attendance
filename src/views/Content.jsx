import { useState } from 'react'
import { CalendarDays, FileText, Megaphone, Plus, Trash2, Upload } from 'lucide-react'
import { api, patch, post } from '../api'
import { Badge, Button, Empty, Heading, Modal, Panel, fmtDate } from '../ui'
import useResource from '../useResource'

const localDate=value=>{if(!value)return '';const d=new Date(value);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
const localTime=value=>value?new Date(value).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',hour12:false}):''

export default function Content({role,refresh,refreshAll,notify,section}) {
  const [tab,setTab]=useState(section==='policies'?'policies':'news')
  const [edit,setEdit]=useState(null)
  const [photos,setPhotos]=useState([])
  const [photoView,setPhotoView]=useState(null)
  const [deleteEvent,setDeleteEvent]=useState(null)
  const [deleting,setDeleting]=useState(false)
  const {data:policies=[],error:pErr}=useResource('/policies',refresh)
  const {data:news=[],error:nErr}=useResource('/news',refresh)
  const {data:events=[],error:eErr}=useResource('/events',refresh)
  const canPolicy=['HR','ADMIN'].includes(role)
  const canNews=['MANAGER','HR','ADMIN'].includes(role)
  const canEvents=['HR','ADMIN'].includes(role)
  const canWrite=tab==='policies'?canPolicy:tab==='news'?canNews:canEvents

  function start(kind,item=null) {
    setPhotos([])
    setEdit({kind,item,title:item?.title||'',body:item?.body||'',description:item?.description||'',starts_at:item?.starts_at||'',ends_at:item?.ends_at||'',location:item?.location||'',status:item?.status||'DRAFT'})
  }
  async function submit(e) {
    e.preventDefault()
    const f=new FormData(e.currentTarget)
    try {
      if(edit.kind==='policies'||edit.kind==='news') {
        const body={title:f.get('title'),body:f.get('body'),status:f.get('status')}
        edit.item?await patch(`/${edit.kind}/${edit.item.id}`,body):await post(`/${edit.kind}`,body)
      } else {
        const body={title:f.get('title'),description:f.get('description'),starts_at:new Date(`${f.get('date')}T${f.get('time')||'12:00'}`).toISOString(),time_unspecified:!f.get('time'),ends_at:f.get('end_date')?new Date(`${f.get('end_date')}T${f.get('end_time')||f.get('time')||'00:00'}`).toISOString():null,location:f.get('location'),status:f.get('status')}
        const item=edit.item?await patch(`/events/${edit.item.id}`,body):await post('/events',body)
        for(const file of photos){const data=new FormData();data.append('file',file);await post(`/events/${item.id}/media`,data)}
      }
      const kind=edit.kind
      setEdit(null);refreshAll();notify(`${kind==='policies'?'Policy':kind==='news'?'News post':'Event'} saved.`)
    } catch(err) {notify(err.message)}
  }
  async function removeEvent() {
    if(!deleteEvent)return
    setDeleting(true)
    try {await api(`/events/${deleteEvent.id}`,{method:'DELETE'});setDeleteEvent(null);refreshAll();notify('Event deleted.')}
    catch(err){notify(err.message)}
    finally{setDeleting(false)}
  }

  return <>
    <Heading title={section==='policies'?'Company policies':'News & Events'} description={section==='policies'?'Read published policies and updates.':'Company announcements, events, and event photos.'} actions={canWrite&&<Button tone="primary" onClick={()=>start(tab)}><Plus size={15}/>{tab==='policies'?'Add policy':tab==='news'?'Post news':'Add event'}</Button>}/>
    {section==='news'&&<div className="tab-row"><button className={tab==='news'?'selected':''} onClick={()=>setTab('news')}><Megaphone size={15}/> News</button><button className={tab==='events'?'selected':''} onClick={()=>setTab('events')}><CalendarDays size={15}/> Events</button></div>}
    {tab==='policies'?<div className="content-grid">{policies.map(p=><Panel key={p.id}><div className="content-card-top"><span className="mini-symbol"><FileText size={17}/></span><Badge tone={p.status==='PUBLISHED'?'green':'gray'}>{p.status}</Badge></div><h2>{p.title}</h2><p className="body-copy">{p.body}</p><div className="content-card-bottom"><small>Version {p.version} · Updated {fmtDate(p.updated_at)}</small>{canPolicy&&<Button onClick={()=>start('policies',p)}>Edit</Button>}</div></Panel>)}{!policies.length&&<Panel><Empty>{pErr||'No policies published yet.'}</Empty></Panel>}</div>:tab==='news'?<Panel>{news.map(n=><article className="news-card" key={n.id}><div className="mini-symbol"><Megaphone size={16}/></div><div className="news-copy"><div className="row-title"><h2>{n.title}</h2><Badge tone={n.status==='PUBLISHED'?'green':'gray'}>{n.status}</Badge></div><p>{n.body}</p><small>Published {fmtDate(n.published_at)}</small></div>{canNews&&<Button onClick={()=>start('news',n)}>Edit</Button>}</article>)}{!news.length&&<Empty>{nErr||'No published news yet.'}</Empty>}</Panel>:<div className="event-grid">{events.map(ev=><Panel key={ev.id}><div className="event-photos">{ev.photos?.map(p=><img key={p.id} src={p.url} alt={p.caption||ev.title} onClick={()=>setPhotoView({url:p.url,alt:p.caption||ev.title})} title="View full image"/>)}{!ev.photos?.length&&<div className="event-placeholder"><CalendarDays size={24}/></div>}</div><div className="event-details"><div className="event-card-heading"><Badge tone={ev.status==='PUBLISHED'?'green':'gray'}>{ev.status}</Badge>{canEvents&&<div className="event-actions"><Button onClick={()=>start('events',ev)}>Edit event</Button><Button tone="danger" onClick={()=>setDeleteEvent(ev)}><Trash2 size={14}/> Delete</Button></div>}</div><h2>{ev.title}</h2><p>{fmtDate(ev.starts_at,{weekday:'long',day:'numeric',month:'long',year:'numeric'})}{!ev.time_unspecified&&` · ${new Date(ev.starts_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`}</p>{ev.location&&<p>{ev.location}</p>}{ev.description&&<p className="body-copy">{ev.description}</p>}</div></Panel>)}{!events.length&&<Panel><Empty>{eErr||'No published events yet.'}</Empty></Panel>}</div>}
    {edit&&<Modal title={`${edit.item?'Edit':'Create'} ${edit.kind==='policies'?'policy':edit.kind==='news'?'news post':'event'}`} description="Content changes are saved to the company database." onClose={()=>setEdit(null)}><form className="form" onSubmit={submit}><label>Title<input name="title" required minLength={2} defaultValue={edit.title}/></label>{edit.kind==='events'?<><div className="form-row"><label>Date<input name="date" type="date" required defaultValue={localDate(edit.starts_at)}/></label><label>Time (optional)<input name="time" type="time" defaultValue={!edit.item?.time_unspecified?localTime(edit.starts_at):''}/></label></div><div className="form-row"><label>End date (optional)<input name="end_date" type="date" defaultValue={localDate(edit.ends_at)}/></label><label>End time (optional)<input name="end_time" type="time" defaultValue={localTime(edit.ends_at)}/></label></div><label>Location<input name="location" defaultValue={edit.location}/></label><label>Description<textarea name="description" defaultValue={edit.description}/></label><label className="upload-control"><Upload size={16}/> Add event photos<input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e=>setPhotos(Array.from(e.target.files||[]))}/></label><small className="muted">Select multiple JPEG, PNG, or WebP images. Click an event photo to view it full size.</small></>:<label>{edit.kind==='policies'?'Policy content':'Message'}<textarea name="body" required minLength={1} defaultValue={edit.body}/></label>}<label>Publish status<select name="status" defaultValue={edit.status}><option value="DRAFT">Draft</option><option value="PUBLISHED">Publish</option></select></label><div className="modal-actions"><Button onClick={()=>setEdit(null)}>Cancel</Button><Button type="submit" tone="primary">Save</Button></div></form></Modal>}
    {deleteEvent&&<Modal title="Delete event?" description={`“${deleteEvent.title}” and its photos will be permanently removed.`} onClose={()=>!deleting&&setDeleteEvent(null)}><div className="modal-actions"><Button disabled={deleting} onClick={()=>setDeleteEvent(null)}>Cancel</Button><Button tone="danger" disabled={deleting} onClick={removeEvent}>{deleting?'Deleting…':'Delete event'}</Button></div></Modal>}
    {photoView&&<Modal className="event-image-modal" title={photoView.alt} onClose={()=>setPhotoView(null)}><img className="event-image-full" src={photoView.url} alt={photoView.alt}/></Modal>}
  </>
}
