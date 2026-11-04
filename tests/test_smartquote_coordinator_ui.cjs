/* Regression tests for beginner-friendly SmartQuote editing, with no browser
   dependencies, customer records, database or external packages. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app/static/quoting-workspace.js'),'utf8');

function field(value=''){return {value:String(value),focus(){this.focused=true;}};}
function makeForm(values){
  const elements={};
  for(const [name,value] of Object.entries(values))
    elements[name]=field(value);
  const submit={textContent:'Add equipment line',disabled:false};
  const cancel={hidden:true};
  return {
    elements,dataset:{}, reportValidity(){return true;},
    querySelector(selector){
      if(selector==='[type="submit"]')return submit;
      if(selector==='#unifiedCancelEquipmentEdit')return cancel;
      return null;
    },
    reset(){
      for(const [name,input] of Object.entries(elements))
        input.value=String(name==='quantity'?1:name==='tier'?'Gold':name==='term_years'?1:name==='discount_percent'?0:'');
      if(elements.discount_percent)elements.discount_percent.value='0';
    },
    submit,cancel,
  };
}
function workspace(){
  const quoteForm=makeForm({
    customer:'Fictional Customer',site:'Fictional Site',
    source_contract_id:'',contact:'',tier:'Gold',term_years:1,
    discount_percent:0,contract_start:'',contract_end:'',
  });
  const equipmentForm=makeForm({
    description:'',item_code:'',
    serial:'',cover_start:'',quantity:1,
  });
  const guide={innerHTML:''},feedback={textContent:''},pricePanel={innerHTML:''};
  const buttons={};
  const table={
    innerHTML:'',
    querySelectorAll(selector){
      const group=selector==='[data-edit-line]'?'editLine':
        selector==='[data-remove-line]'?'removeLine':null;
      if(!group)return [];
      const attr=group==='editLine'?'edit-line':'remove-line';
      const found=[...this.innerHTML.matchAll(new RegExp('data-'+attr+'="(\\d+)"','g'))];
      return found.map((match)=>{
        const btn={dataset:{[group]:match[1]},handler:null,addEventListener(kind,fn){this.handler=fn;},click(){this.handler();}};
        buttons[selector+match[1]]=btn;
        return btn;
      });
    },
    querySelector(selector){
      if(selector!=='#unifiedUndoEquipmentRemove'||
         !this.innerHTML.includes('id="unifiedUndoEquipmentRemove"'))return null;
      const btn={handler:null,addEventListener(kind,fn){this.handler=fn;},click(){this.handler();}};
      buttons.undo=btn;
      return btn;
    },
  };
  const nodes={
    '#unifiedDraftForm':quoteForm,
    '#unifiedEquipmentAdd':equipmentForm,
    '#unifiedEquipmentTable':table,
    '#quoteCoordinatorGuide':guide,
    '#unifiedDraftFeedback':feedback,
    '#unifiedPricePanel':pricePanel,
    '#unifiedDraftTitle':{textContent:''},
    '#unifiedDraftSave':{disabled:false},'#unifiedSaveAndPrice':{disabled:false},
  };
  const confirms=[];
  const ctx={
    document:{querySelector(selector){return nodes[selector]||null;}},
    window:{confirm(question){confirms.push(question);return ctx.confirmResult;}},
    FormData:class {
      constructor(form){this.values=Object.entries(form.elements).map(([key,control])=>[key,control.value]);}
      entries(){return this.values[Symbol.iterator]();}
    },
    esc(value){return String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;');},
    view:'quoting',
    confirmResult:true,
    api:async()=>{throw Error('No remote API may be used during UI unit tests');},
  };
  vm.createContext(ctx);
  vm.runInContext(source,ctx);
  return {ctx,quoteForm,equipmentForm,guide,feedback,table,buttons,confirms,
    run:(code)=>vm.runInContext(code,ctx)};
}

test('coordinator guide flags unsaved changes and blocks accidental draft loss',()=>{
  const w=workspace();
  w.run('unifiedLastSavedDraftState=unifiedDraftSnapshot()');
  assert.equal(w.run('unifiedDraftHasUnsavedChanges()'),false);
  w.quoteForm.elements.customer.value='Another Customer';
  assert.equal(w.run('unifiedDraftHasUnsavedChanges()'),true);
  w.ctx.confirmResult=false;
  w.run('unifiedNewDraft()');
  assert.equal(w.quoteForm.elements.customer.value,'Another Customer');
  assert.match(w.confirms[0],/Discard unsaved changes/);
  w.ctx.confirmResult=true;
  w.run('unifiedNewDraft()');
  assert.equal(w.quoteForm.elements.customer.value,'');
  assert.equal(w.run('unifiedDraftHasUnsavedChanges()'),false);
});

test('editing equipment changes the existing line without duplicating it',()=>{
  const w=workspace();
  w.run('unifiedEquipment=[{description:"Example Bench",item_code:"TEST-001",serial:"SER-001",cover_start:"",quantity:1}]');
  w.run('renderUnifiedEquipment()');
  w.buttons['[data-edit-line]0'].click();
  assert.equal(w.equipmentForm.elements.serial.value,'SER-001');
  assert.equal(w.equipmentForm.submit.textContent,'Save equipment changes');
  w.equipmentForm.elements.serial.value='SER-CORRECTED';
  w.run('unifiedAddEquipment({preventDefault(){},currentTarget:document.querySelector("#unifiedEquipmentAdd")})');
  const result=JSON.parse(w.run('JSON.stringify(unifiedEquipment)'));
  assert.equal(result.length,1);
  assert.equal(result[0].serial,'SER-CORRECTED');
  assert.equal(w.equipmentForm.submit.textContent,'Add equipment line');
  assert.equal(w.run('unifiedEditingEquipmentIndex'),null);
});

test('removing equipment can be undone without losing the SKU or serial',()=>{
  const w=workspace();
  w.run('unifiedEquipment=[{description:"Example Bench",item_code:"TEST-001",serial:"SER-001",cover_start:"",quantity:1}]');
  w.run('renderUnifiedEquipment()');
  w.buttons['[data-remove-line]0'].click();
  assert.equal(w.run('unifiedEquipment.length'),0);
  assert.match(w.table.innerHTML,/Undo last removal/);
  w.buttons.undo.click();
  const item=JSON.parse(w.run('JSON.stringify(unifiedEquipment[0])'));
  assert.equal(item.item_code,'TEST-001');
  assert.equal(item.serial,'SER-001');
  assert.equal(w.run('unifiedEquipment.length'),1);
});

test('quote cannot be saved while equipment correction is unfinished',async()=>{
  const w=workspace();
  w.run('unifiedEquipment=[{description:"Example Bench",item_code:"TEST-001",serial:"SER-001",cover_start:"",quantity:1}]');
  w.run('renderUnifiedEquipment()');
  w.buttons['[data-edit-line]0'].click();
  const result=await w.run('unifiedSaveDraft()');
  assert.equal(result,null);
  assert.match(w.feedback.textContent,/Save or cancel the equipment line/);
});

test('guide does not mistake a priced line for a commercial approval',()=>{
  const w=workspace();
  w.run('unifiedEquipment=[{description:"Example Bench",item_code:"TEST-001",serial:"SER-001",cover_start:"",quantity:1}]');
  w.run('unifiedDraftSelected={id:"d".repeat(32),revision:1}');
  w.run('unifiedLastSavedDraftState=unifiedDraftSnapshot()');
  w.run('unifiedLatestPricePreview={complete_price:true}');
  w.run('unifiedCoordinatorGuidance()');
  assert.match(w.guide.innerHTML,/Step 4 of 4/);
  assert.match(w.guide.innerHTML,/manager approval checks/);
  assert.doesNotMatch(w.guide.innerHTML,/approved quotation ready/i);
});


test('invoice recognition is candidate evidence, never automatic equipment eligibility',()=>{
  const w=workspace();
  const input={
    evidence:{equipment_codes:[
      {value:'test-001',pages:[2,3,2]},
      {value:'TEST-001',pages:[2]},
      {value:"'); alert(1)",pages:[9]},
      {value:'PART-2',pages:[4]},
    ]},
    catalogue_matches:{'TEST-001':{name:'Fictional Bike'}},
  };
  const list=JSON.parse(w.run('JSON.stringify(unifiedInvoiceCandidates('+JSON.stringify(input)+'))'));
  assert.equal(list.length,2);
  assert.equal(list[0].sku,'TEST-001');
  assert.deepEqual(list[0].pages,[2,3,2]);
  assert.equal(list[0].description,'Fictional Bike');
  assert.equal(list[0].identity_not_verified,true);
  assert.equal(list[0].quantity_not_inferred,true);
  assert.equal(list[0].serials_not_inferred,true);
});

test('invoice provenance remains on unchanged code and detaches on changed code',()=>{
  const w=workspace();
  w.equipmentForm.elements.description.value='Example Bench';
  w.equipmentForm.elements.item_code.value='TEST-001';
  w.equipmentForm.elements.serial.value='SER-001';
  w.equipmentForm.dataset.invoiceSku='TEST-001';
  w.equipmentForm.dataset.invoiceSourceId='17';
  w.equipmentForm.dataset.invoicePages='[2,3]';
  w.run('unifiedAddEquipment({preventDefault(){},currentTarget:document.querySelector("#unifiedEquipmentAdd")})');
  let item=JSON.parse(w.run('JSON.stringify(unifiedEquipment[0])'));
  assert.equal(item.source_import_id,17);
  assert.deepEqual(item.source_pages,[2,3]);
  w.run('renderUnifiedEquipment()');
  w.buttons['[data-edit-line]0'].click();
  w.equipmentForm.elements.item_code.value='CORRECTED-SKU';
  w.run('unifiedAddEquipment({preventDefault(){},currentTarget:document.querySelector("#unifiedEquipmentAdd")})');
  item=JSON.parse(w.run('JSON.stringify(unifiedEquipment[0])'));
  assert.equal(item.source_import_id,null);
  assert.deepEqual(item.source_pages,[]);
});


test('pending unadded machine is never silently lost or omitted from a saved quote',async()=>{
  const w=workspace();
  w.run('unifiedLastSavedDraftState=unifiedDraftSnapshot()');
  assert.equal(w.run('unifiedDraftHasUnsavedChanges()'),false);
  w.equipmentForm.elements.description.value='An unfinished treadmill';
  w.equipmentForm.elements.item_code.value='UNFINISHED-1';
  assert.equal(w.run('unifiedHasPendingEquipmentInput()'),true);
  assert.equal(w.run('unifiedDraftHasUnsavedChanges()'),true);
  const result=await w.run('unifiedSaveDraft()');
  assert.equal(result,null);
  assert.match(w.feedback.textContent,/Add equipment line first/);
  w.ctx.confirmResult=false;
  w.run('unifiedNewDraft()');
  assert.equal(w.equipmentForm.elements.item_code.value,'UNFINISHED-1');
  assert.match(w.confirms[0],/Discard unsaved changes/);
});
