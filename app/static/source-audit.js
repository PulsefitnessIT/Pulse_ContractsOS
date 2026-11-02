/* Factual private source auditing; never assume a file has been deployed. */
async function sourceAuditPage() {
  content.innerHTML = '<div class="main-inner"><h2>Master Source Audit</h2><p>Checking the approved private Maintenance Master and its database provenance…</p></div>';
  try {
    const info = await api('/api/pilot/master-source-audit');
    if (view !== 'source_audit') return;
    const active = info.registers['Maintenance Database'];
    const expired = info.registers['Expired'];
    const counts = [
      ['Current source rows', active.populated_site_rows, info.database_rows.active],
      ['Expired source rows', expired.populated_site_rows, info.database_rows.expired],
    ];
    const rows = counts.map(([title,source,stored]) => '<tr><td>' + esc(title) +
      '</td><td>' + esc(source) + '</td><td>' + esc(stored) + '</td><td>' +
      (source === stored ? 'Counts agree' : 'Review required') + '</td></tr>').join('');
    const duplicates = info.source_id_duplicates.affected_source_rows || [];
    const entries = (details) => Object.entries(details).map(([name,count]) =>
      '<tr><td>' + esc(name) + '</td><td>' + esc(count) + '</td></tr>').join('');
    const labelRows = Object.entries(active.cover_labels_as_recorded).map(([label,count]) =>
      '<tr><td>' + esc(label) + '</td><td>' + esc(count) + '</td></tr>').join('');
    content.innerHTML =
      '<div class="main-inner"><section class="card panel"><h2>Maintenance Master — factual source status</h2>' +
      '<p><strong>Workbook fingerprint:</strong> <code>' + esc(info.workbook_sha256) + '</code></p>' +
      '<p><strong>Source matches last recorded import:</strong> ' +
      (info.source_file_matches_last_load ? 'Yes' : 'No / not proven') + '</p>' +
      '<p><strong>Latest working Master upload:</strong> ' +
      (info.last_working_master_upload
        ? esc(info.last_working_master_upload.status) + ' · ' +
          esc(info.last_working_master_upload.submitted_at) +
          ' · <code>' + esc(info.last_working_master_upload.sha256) + '</code>'
        : 'No recurring uploads recorded') + '</p>' +
      '<p><strong>Approved field-update actions:</strong> ' +
      esc(info.reviewed_working_master_updates?.approved_field_update_actions || 0) +
      (info.reviewed_working_master_updates?.last_applied_at ?
        ' · Last applied ' + esc(info.reviewed_working_master_updates.last_applied_at) : '') + '</p>' +
      '<p><strong>Workbook and register counts:</strong> ' +
      (info.record_counts_match ? 'Row counts agree' : 'Mismatch — investigate before relying on reports') + '</p>' +
      '<p>Source-backed means the values came from Excel. It does not prove that Sage, Sicon, signed agreements or bank receipts agree.</p>' +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>' +
      '<th>Register</th><th>Workbook rows</th><th>Database rows</th><th>Comparison</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div></section>' +
      '<section class="card panel"><h3>Current financial fields as recorded</h3>' +
      '<p>Missing contract amounts are not treated as zero. These counts are not verified revenue.</p>' +
      '<table class="data-table"><thead><tr><th>Amount condition</th><th>Records</th></tr></thead><tbody>' +
      entries(active.amounts_as_recorded) + '</tbody></table>' +
      '<h4>Missing source details</h4><table class="data-table"><thead><tr><th>Field</th><th>Records</th></tr></thead><tbody>' +
      entries(active.missing_fields) + '</tbody></table></section>' +
      '<section class="card panel"><h3>Cover descriptions exactly as recorded</h3>' +
      '<p>These are original labels, not inferred contract/warranty classifications. The governing agreement determines cover.</p>' +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Recorded cover label</th><th>Current records</th></tr></thead><tbody>' +
      labelRows + '</tbody></table></div></section>' +
      '<section class="card panel"><h3>Source identification exceptions</h3>' +
      '<p><strong>' + esc(info.source_id_duplicates.extra_duplicate_rows) + '</strong> duplicate source Record ID occurrence(s).</p>' +
      '<p>' + (duplicates.length ? 'Affected Excel worksheet rows: ' +
        duplicates.map(x => esc(x.sheet) + ' row ' + esc(x.row)).join('; ') :
        'No repeated source Record IDs detected.') + '</p>' +
      '<p>When an identifier is repeated, the import preserves the original identifier in the record and uses a separate labelled internal key.</p>' +
      '<p><strong>Verification level:</strong> source-derived, not financially or contractually certified. ' +
      'No Sage/Sicon records are changed by this audit.</p></section></div>';
    showRecurringMasterUpload().catch(error => { const host=document.querySelector('#masterSyncArea'); if(host) host.textContent=error.message; });
  } catch (error) {
    if (view !== 'source_audit') return;
    content.innerHTML = '<div class="main-inner"><section class="card panel">' +
      '<h2>Master Source Audit</h2><p>The approved private workbook or database could not be verified.</p>' +
      '<p class="notice warning">' + esc(error.message) + '</p>' +
      '<p>Do not substitute a fictional demo or a historical workbook for the current approved Master.</p>' +
      '</section></div>';
  }
}


async function showRecurringMasterUpload() {
  const status = await api('/api/pilot/me');
  if (view !== 'source_audit' || !status.pilot || status.role !== 'Admin') return;
  const outer = document.querySelector('#content .main-inner');
  if (!outer) return;
  const section = document.createElement('section');
  section.className = 'card panel';
  section.id = 'masterSyncArea';
  section.innerHTML =
    '<h2>Upload the latest working Maintenance Master</h2>' +
    '<p>Excel remains your working document during the transition. Upload the complete current eight-sheet .xlsx file whenever it changes. This compares it to the last recognised source baseline, without replacing the platform database.</p>' +
    '<form id="masterSyncUploadForm">' +
    '<label>Current Maintenance Master <input type="file" name="file" accept=".xlsx" required></label> ' +
    '<button type="submit" class="button button-primary">Preview changes</button></form>' +
    '<p class="fine-print">Administrator review required. Missing and moved records are flagged, never deleted or expired. The source workbook stays private on the server.</p>' +
    '<div id="masterSyncResults" aria-live="polite"></div>';
  outer.prepend(section);
  section.querySelector('#masterSyncUploadForm').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.querySelector('input[type=file]');
    const button = form.querySelector('button[type=submit]');
    const results = document.querySelector('#masterSyncResults');
    if (!input.files || input.files.length !== 1) return;
    button.disabled = true;
    results.textContent = 'Validating the uploaded workbook and comparing source records…';
    try {
      const payload = new FormData();
      payload.append('file', input.files[0]);
      const report = await api('/api/pilot/master-sync/preview', {method:'POST',body:payload});
      if (view !== 'source_audit' || !document.querySelector('#masterSyncResults')) return;
      renderMasterSyncReview(report);
    } catch (error) {
      if (results) results.textContent = 'No changes applied. ' + error.message;
    } finally {
      button.disabled = false;
    }
  });
}

function renderMasterSyncReview(report) {
  const host = document.querySelector('#masterSyncResults');
  if (!host) return;
  const summary = report.summary || {};
  const cards = Object.entries({
    'Safe existing-record updates':summary.safe_updates || 0,
    'Already current':summary.unchanged_or_already_current || 0,
    'New/unmatched records':summary.new_or_unmatched || 0,
    'Ambiguous IDs':summary.ambiguous_rows || 0,
    'Moved / changed status':summary.moves_requiring_review || 0,
    'Conflicting existing edits':summary.conflicts || 0,
    'Absent from upload (not deleted)':summary.missing_or_removed_from_workbook || 0,
  }).map(([label,n]) => '<tr><td>' + esc(label) + '</td><td>' + esc(n) + '</td></tr>').join('');
  const shown = (report.items || []).slice(0,250);
  const actionable = shown.map((r,idx) =>
    '<tr><td><input type="checkbox" name="masterReviewIndex" value="' + idx +
    '" aria-label="Approve update ' + esc(idx+1) + '"></td><td>' + esc(r.row_key) +
    '</td><td>' + esc(r.sheet) + ' / ' + esc(r.source_row) +
    '</td><td>' + r.changes.map(c => '<strong>' + esc(c.field) + '</strong>: ' +
    esc(c.in_platform) + ' → ' + esc(c.in_workbook)).join('; ') + '</td></tr>').join('');
  const blocked = (report.review_required || []).slice(0,60).map(row =>
    '<tr><td>' + esc(row.sheet) + ' / ' + esc(row.source_row) +
    '</td><td>' + esc(row.reason) + '</td></tr>').join('');
  host.innerHTML =
    '<section class="panel"><h3>Upload review — no changes applied</h3>' +
    '<p><strong>Filename:</strong> ' + esc(report.filename) + ' · <strong>SHA-256:</strong> <code>' +
    esc(report.sha256) + '</code></p>' +
    '<p>Source rows — Maintenance Database: ' + esc(report.registers['Maintenance Database']) +
    ' · Expired: ' + esc(report.registers.Expired) + '</p>' +
    '<table class="data-table"><thead><tr><th>Comparison</th><th>Rows</th></tr></thead><tbody>' +
    cards + '</tbody></table>' +
    '<h4>Safe field updates — choose only those you have checked</h4>' +
    '<p>Selections are not automatic. Up to 250 records can be applied per review; re-upload the latest file for the remaining changes.</p>' +
    '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Select</th><th>Source ID</th><th>Worksheet row</th><th>Current → incoming values</th></tr></thead><tbody>' +
    (actionable || '<tr><td colspan="4">No conflict-free existing-record changes to apply.</td></tr>') +
    '</tbody></table></div>' +
    (report.items.length > shown.length ? '<p>' +
     esc(report.items.length - shown.length) + ' additional safe updates are not displayed. Apply reviewed records, then upload again.</p>' : '') +
    '<h4>Human-review exceptions</h4>' +
    '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Source row</th><th>Reason</th></tr></thead><tbody>' +
    (blocked || '<tr><td colspan="2">No new exceptions detected.</td></tr>') +
    '</tbody></table></div>' +
    (report.review_required_total > blocked.length ? '<p>' + esc(report.review_required_total - blocked.length) +
     ' additional exceptions are not displayed here.</p>' : '') +
    '<button id="masterSyncApply" type="button" class="button button-primary"' +
    (shown.length ? '' : ' disabled') + '>Apply selected safe updates</button>' +
    '<p id="masterSyncFeedback" role="status"></p></section>';
  const button = host.querySelector('#masterSyncApply');
  button.addEventListener('click',async () => {
    const selected = [...host.querySelectorAll('input[name=masterReviewIndex]:checked')]
      .map(input => Number(input.value));
    const feedback = host.querySelector('#masterSyncFeedback');
    if (!selected.length) { feedback.textContent='Select at least one reviewed change.';return; }
    if (!window.confirm('Apply ' + selected.length +
        ' selected workbook updates to Contracts OS? This will preserve other fields, equipment and historical data.')) return;
    button.disabled = true;
    feedback.textContent = 'Applying selected changes with revision checks…';
    try {
      const result = await api(
        '/api/pilot/master-sync/' + encodeURIComponent(report.review_id) + '/apply',
        {method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({approved_items:selected})}
      );
      feedback.textContent = 'Applied ' + result.approved_records_updated +
        ' selected records; none were archived or deleted. ' +
        (result.requires_new_upload_to_continue ?
        'Upload the latest file again to review remaining updates.' :
        'This review is complete.');
      if (typeof refreshMeta === 'function') await refreshMeta();
    } catch(error) {button.disabled = false;feedback.textContent='No updates applied. ' + error.message;}
  });
}
