// Copyright (c) 2020 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
import * as StringUtilities from './string-utilities.js';
import { localize } from './UIString.js';
export const clamp = (num, min, max) => {
    let clampedNumber = num;
    if (num < min) {
        clampedNumber = min;
    }
    else if (num > max) {
        clampedNumber = max;
    }
    return clampedNumber;
};
export const mod = (m, n) => {
    return ((m % n) + n) % n;
};
export const bytesToString = (bytes) => {
    if (bytes < 1000) {
        return StringUtilities.vsprintf(localize('%.0f\xA0B'), [bytes]);
    }
    const kilobytes = bytes / 1000;
    if (kilobytes < 100) {
        return StringUtilities.vsprintf(localize('%.1f\xA0kB'), [kilobytes]);
    }
    if (kilobytes < 1000) {
        return StringUtilities.vsprintf(localize('%.0f\xA0kB'), [kilobytes]);
    }
    const megabytes = kilobytes / 1000;
    if (megabytes < 100) {
        return StringUtilities.vsprintf(localize('%.1f\xA0MB'), [megabytes]);
    }
    return StringUtilities.vsprintf(localize('%.0f\xA0MB'), [megabytes]);
};
export const toFixedIfFloating = (value) => {
    if (!value || Number.isNaN(Number(value))) {
        return value;
    }
    const number = Number(value);
    return number % 1 ? number.toFixed(3) : String(number);
};
/**
 * Rounds a number (including float) down.
 */
export const floor = (value, precision = 0) => {
    const mult = Math.pow(10, precision);
    return Math.floor(value * mult) / mult;
};
//# sourceMappingURL=number-utilities.js.map