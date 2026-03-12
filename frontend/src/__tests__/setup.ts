// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import "@testing-library/jest-dom";

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {};