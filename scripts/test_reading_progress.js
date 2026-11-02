const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync('assets/js/app.js', 'utf8').split("window.addEventListener('online'")[0];

function makeReader(scrollY) {
    const window = { scrollY, innerHeight: 800, visualViewport: null, scrollTo(options) { this.lastScroll = options; } };
    const last = { getBoundingClientRect: () => ({ bottom: 3000 - window.scrollY }) };
    const nodes = {
        articleBody: { lastElementChild: last },
        readingDock: { hidden: false, getBoundingClientRect: () => ({ top: 720 }) },
        articleContinue: { hidden: false },
    };
    const document = { getElementById: id => nodes[id] || null };
    const context = vm.createContext({ window, document, console,
        localStorage: { getItem: key => key === 'reading_position' ? JSON.stringify({ u1: { r: 0.5 } }) : null },
        setTimeout: fn => fn() });
    vm.runInContext(source, context);
    return context;
}

test('阅读进度在正文结束处为 100%，不受后方相关阅读影响', () => {
    const halfway = makeReader(1140);
    const finished = makeReader(2280);
    assert.equal(vm.runInContext('getArticleProgressRatio()', halfway), 0.5);
    assert.equal(vm.runInContext('getArticleProgressRatio()', finished), 1);
});

test('继续阅读使用与进度环相同的正文终点', () => {
    const reader = makeReader(0);
    vm.runInContext("state.currentArticleUrl='u1';continueReading()", reader);
    assert.equal(reader.window.lastScroll.top, 1140);
});
