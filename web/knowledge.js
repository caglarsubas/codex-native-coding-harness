"use strict";
const knowledgeUi = new Map();

function projectKnowledge(root) {
  const repos=(state?.repositories||[]).filter(r=>r.policyProfile==='standard');
  if(!repos.length)return;
  const project=workspaceId, model=knowledgeUi.get(project)||{repository:repos[0].id,query:'',status:null,search:null,records:null,related:null,source:null,error:null};
  knowledgeUi.set(project,model);
  root.append(section('Project knowledge','Search bounded, cited code from an explicitly configured private index. Git and the project ledger remain authoritative.'));
  const controls=el('div',null,'inline-actions'),selector=el('select');
  selector.setAttribute('aria-label','Repository for knowledge search');
  for(const repo of repos){const option=el('option',repo.id);option.value=repo.id;selector.append(option);}
  selector.value=model.repository;
  selector.onchange=()=>{model.repository=selector.value;model.status=null;model.search=null;model.records=null;model.related=null;model.source=null;render();};
  const input=el('input');input.type='search';input.placeholder='Find a symbol, concept or path';input.value=model.query;
  input.setAttribute('aria-label','Search project knowledge');
  controls.append(selector,input);
  const loadStatus=async()=>{
    try{model.status=await api('/api/knowledge/status?'+new URLSearchParams({repository:model.repository}));model.error=null;}
    catch(error){if(!error.workspaceChanged)model.error=error.message;}
    if(workspaceId===project)render();
  };
  controls.append(button('Index status',loadStatus),button('Refresh local index',async()=>{
    try{model.status=await api('/api/knowledge/refresh',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({repository:model.repository})});model.search=null;model.error=null;}
    catch(error){if(!error.workspaceChanged)model.error=error.message;}
    if(workspaceId===project)render();
  }),button('Search',async()=>{
    model.query=input.value;
    try{
      [model.search,model.records]=await Promise.all([
        api('/api/knowledge/search?'+new URLSearchParams({repository:model.repository,query:model.query})),
        api('/api/knowledge/records?'+new URLSearchParams({repository:model.repository,query:model.query}))]);
      model.source=null;model.related=null;model.error=null;
    }
    catch(error){if(!error.workspaceChanged)model.error=error.message;}
    if(workspaceId===project)render();
  }));
  root.append(controls);
  if(model.error)root.append(callout('Knowledge unavailable',model.error));
  if(model.status)root.append(el('p',`${model.status.status} · ${model.status.fileCount||0} files · revision ${model.status.commit||'unknown'} · observed ${when(model.status.observedAt)} · Graphify ${model.status.provider?.status||model.status.provider}`,'subline'));
  if(model.status?.coverageGaps?.length)root.append(el('p','Coverage: '+model.status.coverageGaps.join('; '),'muted'));
  if(model.search){
    root.append(el('p',`${model.search.status} · ${model.search.coverage} · ${model.search.truncated?'Results truncated':'All matching results shown'}`,'subline'));
    if(!model.search.results.length)root.append(el('p','No match in the indexed code. This does not establish that the project has no answer.','muted'));
    for(const hit of model.search.results){
      const card=el('section',null,'detail');
      card.append(el('h3',hit.path+':'+hit.line),el('p',hit.excerpt,'mono'),el('p',`${hit.provenance} · ${hit.commit} · index ${hit.indexHash}`,'subline'));
      card.append(button('Read cited source',async()=>{
        try{
          const direct=!hit.indexHash;
          const params=direct?{repository:hit.repository,commit:hit.commit,blob:hit.blob,path:hit.path,line:String(hit.line)}:{repository:hit.repository,indexHash:hit.indexHash,path:hit.path,line:String(hit.line)};
          model.source=await api('/api/knowledge/'+(direct?'direct-source':'source')+'?'+new URLSearchParams(params));model.error=null;
        }
        catch(error){if(!error.workspaceChanged)model.error=error.message;}
        if(workspaceId===project)render();
      }));
      if(hit.indexHash)card.append(button('Related items',async()=>{
        try{model.related=await api('/api/knowledge/related?'+new URLSearchParams({repository:hit.repository,indexHash:hit.indexHash,path:hit.path}));model.error=null;}
        catch(error){if(!error.workspaceChanged)model.error=error.message;}
        if(workspaceId===project)render();
      }));root.append(card);
    }
    if(model.source)root.append(section('Cited Git source',model.source.path+' · '+model.source.commit),el('pre',model.source.excerpt,'detail'));
    if(model.related){
      root.append(section('Graph relationships',model.related.status==='ready'?'Extracted and inferred links are labeled separately.':'Graphify unavailable; source search remains available.'));
      for(const item of model.related.items||[])root.append(el('p',`${item.path} · ${item.relation} · ${item.provenance} · ${item.commit}`,'subline'));
    }
  }
  if(model.records){
    root.append(section('Existing project records','Links to retained roadmap, decision and artifact versions; contents are not copied into the index.'));
    for(const record of model.records.records){
      const row=el('div',null,'detail');row.append(el('p',`${record.kind} · ${record.title} · v${record.version} · ${record.provenance}`,'subline'));
      row.append(button('Open recorded version',()=>navigateView(record.kind==='decision'?'decisions':'artifacts',record.id)));
      root.append(row);
    }
    if(model.records.truncated)root.append(el('p','Record links truncated to ten results. Narrow the query.','muted'));
  }
}
