'use strict';
// The file field of the action form of LoadDownloadAdminMixin: shown only for the actions
// that load a file (bg-actions-task-load, rendered by admin/bg/load_download_change_list.html).
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('changelist-form');
    const data = document.getElementById('bg-actions-task-load');
    const action = form && form.querySelector('[name="action"]');
    const fileLoad = form && form.querySelector('[name="file_load"]');
    if (!action || !fileLoad) {
        return;
    }
    const loads = (data && JSON.parse(data.textContent)) || [];
    const toggle = function () {
        fileLoad.parentElement.style.display = loads.includes(action.value) ? '' : 'none';
    };
    action.addEventListener('change', toggle);
    toggle();
});
