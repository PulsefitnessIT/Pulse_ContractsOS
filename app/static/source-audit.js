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
  } catch (error) {
    if (view !== 'source_audit') return;
    content.innerHTML = '<div class="main-inner"><section class="card panel">' +
      '<h2>Master Source Audit</h2><p>The approved private workbook or database could not be verified.</p>' +
      '<p class="notice warning">' + esc(error.message) + '</p>' +
      '<p>Do not substitute a fictional demo or a historical workbook for the current approved Master.</p>' +
      '</section></div>';
  }
}
