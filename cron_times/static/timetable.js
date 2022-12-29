'use strict';

function gotoNow() {
    document.getElementById('timecard-now')
        .scrollIntoView({ block: 'center' });
}

// initialize
(function () {
    // 'now' button
    document.getElementById('gotoNow')
        .addEventListener('click', gotoNow);
})();
