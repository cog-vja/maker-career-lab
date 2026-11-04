/* Progressive enhancement only. Rankings remain crawlable HTML when JS is disabled. */
(function () {
  'use strict';
  document.querySelectorAll('[data-mcl-table-search]').forEach(function (input) {
    var target = document.getElementById(input.getAttribute('data-mcl-table-search'));
    if (!target) return;
    var rows = Array.from(target.querySelectorAll('tbody tr'));
    var count = document.getElementById(input.getAttribute('aria-controls') + '-count');
    input.addEventListener('input', function () {
      var q = input.value.trim().toLocaleLowerCase('ja-JP');
      var visible = 0;
      rows.forEach(function (row) {
        var searchable = (row.getAttribute('data-company') || '') + ' ' + (row.getAttribute('data-sector') || '');
        var show = searchable.toLocaleLowerCase('ja-JP').includes(q);
        row.hidden = !show;
        if (show) visible += 1;
      });
      if (count) count.textContent = '表示中 ' + visible + ' / ' + rows.length + ' 社（上位100社の範囲内）';
    });
  });
})();
