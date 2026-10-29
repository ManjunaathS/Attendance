import { useEffect, useState } from 'react'
import { get } from './api'
const fallbackFor=path=>path?.includes('/balances/me')||path?.includes('/attendance/config')||path?.includes('/organization/tree')?null:[]
export default function useResource(path,refresh=0,enabled=true){const fallback=fallbackFor(path),[data,setData]=useState(fallback),[loading,setLoading]=useState(enabled),[error,setError]=useState('');useEffect(()=>{if(!enabled||!path)return;let live=true;setLoading(true);get(path).then(x=>{if(live){setData(x??fallbackFor(path));setError('')}}).catch(e=>live&&setError(e.message)).finally(()=>live&&setLoading(false));return()=>{live=false}},[path,refresh,enabled]);return{data,loading,error,setData}}
