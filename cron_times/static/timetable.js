'use strict';

function gotoNow() {
    document.getElementById('timecard-now')
        .scrollIntoView({ block: 'center' });
}

/**
 * @param {HTMLElement} card
 * @param {string} timezone
 */
function updateTaskCardTime(card, timezone) {
    // get job run time
    let domBriefTime = card.querySelector('.time'),
        dateTime = dayjs(domBriefTime.dataset.datetime).tz(timezone);

    // update brief time
    let briefTime = '';
    if (!dateTime.isToday()) {
        if (dateTime.isTomorrow()) {
            briefTime = 'Tomorrow';
        } else if (dateTime.isYesterday()) {
            briefTime = 'Yesterday';
        } else {
            briefTime = dateTime.format('MMM DD');
        }
    }

    briefTime += `<h4>${dateTime.format('HH:mm')}</h4>`;

    domBriefTime.innerHTML = briefTime

    // update detailed exec time
    let detailTimeLabel = card.querySelector('.detail-time');
    if (detailTimeLabel) {
        detailTimeLabel.innerHTML = dateTime.format('YYYY-MM-DD HH:mm:ss Z');
    }

    let relativeTimeLabel = card.querySelector('.relative-time');
    if (relativeTimeLabel) {
        relativeTimeLabel.innerHTML = dateTime.from();
    }
}

// initialize
(function () {
    // 'now' button
    document.getElementById('gotoNow')
        .addEventListener('click', gotoNow);
})();
