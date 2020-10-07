// /api/event/?event=$autocapture&properties[pathname]=/docs/introduction/what-is-kea

import { kea } from 'kea'
import { encodeParams } from 'kea-router'
import { currentPageLogic } from '~/toolbar/stats/currentPageLogic'
import { elementToActionStep, elementToSelector, trimElement } from '~/toolbar/utils'
import { toolbarLogic } from '~/toolbar/toolbarLogic'
import { heatmapLogicType } from 'types/toolbar/elements/heatmapLogicType'
import { HeatmapElement, ElementsEventType } from '~/toolbar/types'
import { ActionStepType } from '~/types'

export const heatmapLogic = kea<heatmapLogicType<ElementsEventType, HeatmapElement, ActionStepType>>({
    actions: {
        enableHeatmap: true,
        disableHeatmap: true,
        setShowHeatmapTooltip: (showHeatmapTooltip: boolean) => ({ showHeatmapTooltip }),
    },

    reducers: {
        heatmapEnabled: [
            false,
            {
                enableHeatmap: () => true,
                disableHeatmap: () => false,
                getEventsFailure: () => false,
            },
        ],
        heatmapLoading: [
            false,
            {
                getEvents: () => true,
                getEventsSuccess: () => false,
                getEventsFailure: () => false,
                resetEvents: () => false,
            },
        ],
        showHeatmapTooltip: [
            false,
            {
                setShowHeatmapTooltip: (_, { showHeatmapTooltip }) => showHeatmapTooltip,
            },
        ],
    },

    loaders: {
        events: [
            [] as ElementsEventType[],
            {
                resetEvents: () => [],
                getEvents: async ({ $current_url }: { $current_url: string }, breakpoint) => {
                    const params = {
                        properties: [{ key: '$current_url', value: $current_url }],
                        temporary_token: toolbarLogic.values.temporaryToken,
                    }
                    const url = `${toolbarLogic.values.apiURL}api/element/stats/${encodeParams(params, '?')}`
                    const response = await fetch(url)
                    const results = await response.json()

                    if (response.status === 403) {
                        toolbarLogic.actions.authenticate()
                        return []
                    }

                    breakpoint()

                    if (!Array.isArray(results)) {
                        throw new Error('Error loading HeatMap data!')
                    }

                    return results
                },
            },
        ],
    },

    selectors: {
        elements: [
            (selectors) => [selectors.events],
            (events) => {
                const elements: HeatmapElement[] = []
                events.forEach((event) => {
                    let combinedSelector
                    let lastSelector
                    for (let i = 0; i < event.elements.length; i++) {
                        const selector = elementToSelector(event.elements[i])
                        combinedSelector = lastSelector ? `${selector} > ${lastSelector}` : selector

                        try {
                            const domElements = Array.from(document.querySelectorAll(combinedSelector)) as HTMLElement[]

                            if (domElements.length === 1) {
                                const e = event.elements[i]

                                // element like "svg" as the first one
                                if (
                                    i === 0 &&
                                    e.tag_name &&
                                    !e.attr_class &&
                                    !e.attr_id &&
                                    !e.href &&
                                    !e.text &&
                                    e.nth_child === 1 &&
                                    e.nth_of_type === 1 &&
                                    !e.attributes['attr__data-attr']
                                ) {
                                    // too simple selector, bail
                                } else {
                                    elements.push({
                                        element: domElements[0],
                                        count: event.count,
                                        selector: selector,
                                        position: -1,
                                    })
                                    return null
                                }
                            }

                            if (domElements.length === 0) {
                                if (i === event.elements.length - 1) {
                                    console.error('Found a case with 0 elements')
                                    return null
                                } else if (i > 0 && lastSelector) {
                                    // We already have something, but found nothing when adding the next selector.
                                    // Skip it and try with the next one...
                                    lastSelector = lastSelector ? `* > ${lastSelector}` : '*'
                                    continue
                                } else {
                                    console.log('Found empty selector')
                                }
                            }
                        } catch (error) {
                            console.error('Invalid selector!', combinedSelector)
                            throw error
                        }

                        lastSelector = combinedSelector

                        // TODO: what if multiple elements will continue to match until the end?
                    }
                })

                return elements.map((e, i) => ({ ...e, position: i + 1 }))
            },
        ],
        countedElements: [
            (selectors) => [selectors.elements],
            (elements) => {
                const elementCounter = new Map<HTMLElement, number>()
                const elementSelector = new Map<HTMLElement, string>()

                ;(elements || []).forEach(({ element, selector, count }) => {
                    const trimmedElement = trimElement(element)
                    if (trimmedElement) {
                        const oldCount = elementCounter.get(trimmedElement) || 0
                        elementCounter.set(trimmedElement, oldCount + count)
                        if (oldCount === 0) {
                            elementSelector.set(trimmedElement, selector)
                        }
                    }
                })

                const countedElements = [] as HeatmapElement[]
                elementCounter.forEach((count, element) => {
                    const selector = elementSelector.get(element)
                    if (selector) {
                        countedElements.push({
                            count,
                            element,
                            selector,
                            position: -1,
                            actionStep: elementToActionStep(element),
                        })
                    }
                })

                countedElements.sort((a, b) => b.count - a.count)

                return countedElements.map((e, i) => ({ ...e, position: i + 1 }))
            },
        ],
        elementCount: [(selectors) => [selectors.countedElements], (countedElements) => countedElements.length],
        clickCount: [
            (selectors) => [selectors.countedElements],
            (countedElements) => (countedElements ? countedElements.map((e) => e.count).reduce((a, b) => a + b, 0) : 0),
        ],
        highestClickCount: [
            (selectors) => [selectors.countedElements],
            (countedElements) =>
                countedElements ? countedElements.map((e) => e.count).reduce((a, b) => (b > a ? b : a), 0) : 0,
        ],
    },

    events: ({ actions, values }) => ({
        afterMount() {
            if (values.heatmapEnabled) {
                actions.getEvents({ $current_url: currentPageLogic.values.href })
            }
        },
    }),

    listeners: ({ actions, values }) => ({
        [currentPageLogic.actionTypes.setHref]: ({ href }) => {
            if (values.heatmapEnabled) {
                actions.resetEvents()
                actions.getEvents({ $current_url: href })
            }
        },
        enableHeatmap: () => {
            actions.getEvents({ $current_url: currentPageLogic.values.href })
        },
        disableHeatmap: () => {
            actions.resetEvents()
            actions.setShowHeatmapTooltip(false)
        },
        getEventsSuccess: () => {
            actions.setShowHeatmapTooltip(true)
        },
        setShowHeatmapTooltip: async ({ showHeatmapTooltip }, breakpoint) => {
            if (showHeatmapTooltip) {
                await breakpoint(1000)
                actions.setShowHeatmapTooltip(false)
            }
        },
    }),
})
