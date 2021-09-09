// Copyright 2020 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
import * as i18n from '../i18n/i18n.js';
import * as Root from '../root/root.js';
export const UIStrings = {
    /**
    *@description Title of the Elements Panel
    */
    elements: 'Elements',
    /**
    *@description Text for DevTools appearance
    */
    appearance: 'Appearance',
    /**
    *@description Name of the Sources panel
    */
    sources: 'Sources',
    /**
    *@description Title of the Network tool
    */
    network: 'Network',
    /**
    *@description Text for the performance of something
    */
    performance: 'Performance',
    /**
    *@description Title of the Console tool
    */
    console: 'Console',
    /**
    *@description A title of the 'Persistence' setting category
    */
    persistence: 'Persistence',
    /**
    *@description Text that refers to the debugger
    */
    debugger: 'Debugger',
    /**
    *@description Text describing global shortcuts and settings that are available throughout the DevTools
    */
    global: 'Global',
    /**
    *@description Title of the Rendering tool
    */
    rendering: 'Rendering',
    /**
    *@description Title of a section on CSS Grid tooling
    */
    grid: 'Grid',
    /**
    *@description Text for the mobile platform, as opposed to desktop
    */
    mobile: 'Mobile',
    /**
    *@description Name of a settings category.
    */
    emulation: 'Emulation',
    /**
    *@description Text for the memory of the page
    */
    memory: 'Memory',
    /**
    *@description Text for the extension of the page
    */
    extension: 'Extension',
};
const str_ = i18n.i18n.registerUIStrings('common/SettingRegistration.ts', UIStrings);
const i18nString = i18n.i18n.getLocalizedString.bind(undefined, str_);
let registeredSettings = [];
const settingNameSet = new Set();
export function registerSettingExtension(registration) {
    const settingName = registration.settingName;
    if (settingNameSet.has(settingName)) {
        throw new Error(`Duplicate setting name '${settingName}'`);
    }
    settingNameSet.add(settingName);
    registeredSettings.push(registration);
}
export function getRegisteredSettings() {
    return registeredSettings.filter(setting => Root.Runtime.Runtime.isDescriptorEnabled({ experiment: setting.experiment, condition: setting.condition }));
}
export function registerSettingExtengionsForTest(settings, forceReset = false) {
    if (registeredSettings.length === 0 || forceReset) {
        registeredSettings = settings;
        settingNameSet.clear();
        for (const setting of settings) {
            const settingName = setting.settingName;
            if (settingNameSet.has(settingName)) {
                throw new Error(`Duplicate setting name '${settingName}'`);
            }
            settingNameSet.add(settingName);
        }
    }
}
export function getLocalizedSettingsCategory(category) {
    switch (category) {
        case "ELEMENTS" /* ELEMENTS */:
            return i18nString(UIStrings.elements);
        case "APPEARANCE" /* APPEARANCE */:
            return i18nString(UIStrings.appearance);
        case "SOURCES" /* SOURCES */:
            return i18nString(UIStrings.sources);
        case "NETWORK" /* NETWORK */:
            return i18nString(UIStrings.network);
        case "PERFORMANCE" /* PERFORMANCE */:
            return i18nString(UIStrings.performance);
        case "CONSOLE" /* CONSOLE */:
            return i18nString(UIStrings.console);
        case "PERSISTENCE" /* PERSISTENCE */:
            return i18nString(UIStrings.persistence);
        case "DEBUGGER" /* DEBUGGER */:
            return i18nString(UIStrings.debugger);
        case "GLOBAL" /* GLOBAL */:
            return i18nString(UIStrings.global);
        case "RENDERING" /* RENDERING */:
            return i18nString(UIStrings.rendering);
        case "GRID" /* GRID */:
            return i18nString(UIStrings.grid);
        case "MOBILE" /* MOBILE */:
            return i18nString(UIStrings.mobile);
        case "EMULATION" /* EMULATION */:
            return i18nString(UIStrings.console);
        case "MEMORY" /* MEMORY */:
            return i18nString(UIStrings.memory);
        case "EXTENSIONS" /* EXTENSIONS */:
            return i18nString(UIStrings.extension);
        case "" /* NONE */:
            return '';
    }
}
//# sourceMappingURL=SettingRegistration.js.map