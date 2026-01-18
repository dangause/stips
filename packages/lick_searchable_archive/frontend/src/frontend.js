import dataDictionary from "../build/scripts/data_dictionary.json"
import config from "./config.json"
import "./theme.js"

import {LoginControls} from "./login_controls.js"
import {LickArchiveClient} from "./lick_archive_client.js"
import {ErrorSection} from "./error_section.js"


const errorSection = new ErrorSection()



const archiveClient = new LickArchiveClient(config.backendURLBase)
const loginControls = new LoginControls(archiveClient, errorSection)

function connectControls(eventType, controllingElemId, controlledElemIds, action) {
    const controllingElem = document.getElementById(controllingElemId)

    if (typeof controlledElemIds == "string") {
        var controlledElems = document.querySelectorAll(controlledElemIds)
    }
    else {
        var controlledElems = []
        for (const elemId of controlledElemIds) {
            controlledElems.push(document.getElementById(elemId))
        }
    }

    function applyAction(event) {
        for (const elem of controlledElems) {
            action(controllingElem, elem)
        }
    }
    controllingElem.addEventListener(eventType, applyAction)
    document.addEventListener("DOMContentLoaded", applyAction)
}

function set_label_disabled_color(controller, controlled) {
    if (controller.checked) {
        controlled.classList.remove("search_terms_label_disabled")
    }
    else {
        controlled.classList.add("search_terms_label_disabled")
    }
}

// Connect the checkbox for each search term to disable/enable its related controls
connectControls("click", "query_by_object",   ["id_object_fields"],      (controller, controlled) => controlled.disabled = !controller.checked)
connectControls("click", "query_by_object",   ["query_by_object_label"], set_label_disabled_color )

connectControls("click", "query_by_obs_date", ["id_date_fields"],          (controller, controlled) => controlled.disabled = !controller.checked)
connectControls("click", "query_by_obs_date", ["query_by_obs_date_label"], set_label_disabled_color )

connectControls("click", "query_by_filename", ["id_filename_fields"],       (controller, controlled) => controlled.disabled = !controller.checked)
connectControls("click", "query_by_filename", ["query_by_filename_label"],  set_label_disabled_color )

connectControls("click", "query_by_coord",    ["id_coords_fields"],     (controller, controlled) => controlled.disabled = !controller.checked)
connectControls("click", "query_by_coord",    ["query_by_coord_label"], set_label_disabled_color )

// Connect the count/results radio boxes to enable/disable the result option fields
connectControls("click", "id_count_0", ["search_option_fields"], (controller, controlled) => controlled.disabled=controller.checked)
connectControls("click", "id_count_1", ["search_option_fields"], (controller, controlled) => controlled.disabled=!controller.checked)

// Connect the second observation date control so that it is hidden when the operator isn't "in"
connectControls("change", "search_operator_obs_date", ["search_value_obs_date_2"], (controller, controlled) => controlled.hidden=(controller.value!='in'))

// Connect the Select ALl/Deselect All to the instrument checkboxes for the Instruments section of the query form
connectControls("click", "instrument_none", "input[id^='instrument_']", (controller, controlled) => controlled.checked=false)
// Weird side effect of the way I did this, connectControls will initialize the controller on DOMContentLoaded, so the "true"
// option must be last to get the checkboxes to default to checked.
connectControls("click", "instrument_all",  "input[id^='instrument_']", (controller, controlled) => controlled.checked=true)



// Deal with the instrument checkbox heirarchy e.g "Kast Blue" and "Kast Red being"
// grouped under "Kast"
document.addEventListener("DOMContentLoaded", setupInstruments)


function setupInstruments(event) {
    for (let i=0; i< config.instrumentOrder.length; i++) {
        const instrKey = config.instrumentOrder[i]
        if (config.instruments[instrKey].category) {
            // Listen for the category check box being clicked, and select/desect the child boxes accordingly
            const categoryCheck = document.getElementById(`instrument_${i}`)
            categoryCheck.addEventListener("click", selectInstrumentCategory)
        }
        else if (config.instruments[instrKey].parent != "") {
            // Listen to the child checkboxes being clicked and select/deslect the category checkbox depending
            // on whether all the children are checked
            const childCheck = document.getElementById(`instrument_${i}`)
            childCheck.addEventListener("click", selectInstrumentChild)
        }
        /* Non child/non-parent checkboxes don't need a listener */
    }
}

/* Called when selecting a "parent" instrument check boxes, it will check/uncheck all its children */
function selectInstrumentCategory(event) {

    for (const childKey of config.instruments[event.target.value].children) {
        const childIndex = config.instrumentOrder.indexOf(childKey)
        const childCheck = document.getElementById(`instrument_${childIndex}`)
        childCheck.checked = event.target.checked
    }
}

/* Called when selecting a instrument that's a "child" of another instrument checkbox. It will check/uncheck its parent
based on the state of the sibling checkboxes */
function selectInstrumentChild(event) {
    const siblings = config.instruments[config.instruments[event.target.value].parent].children
    let checkedSiblings = 0
    for (const siblingKey of siblings) {
        const siblingIndex = config.instrumentOrder.indexOf(siblingKey)
        const siblingCheck = document.getElementById(`instrument_${siblingIndex}`)
        if (siblingCheck.checked) {
            checkedSiblings++
        }
    }
    const parentIndex = config.instrumentOrder.indexOf(config.instruments[event.target.value].parent)
    const parentCheck = document.getElementById(`instrument_${parentIndex}`)
    if (checkedSiblings == siblings.length) {
        parentCheck.checked = true
    }
    else {
        parentCheck.checked = false
    }
}


// Connect the submitQuery button
const submitQueryButton = document.getElementById("submit_query")
submitQueryButton.addEventListener("click", submitQuery)



// Build query parameters from the search form, submit them to the back end
// and display the results
async function submitQuery(event) {
    const queryParams = buildQueryParams(event.target.value)

    const queryURL = queryParamsToString(queryParams)
    console.log(queryURL.toString())
    const results = await archiveClient.runQuery(queryURL)

    processResults(queryParams, results)
}

// Build the query parameters from the search form.
// The parameters are returned in a Map
function buildQueryParams(page) {
    const queryParams = new Map()

    // Build the query parms for the primary indexed serch terms
    for (const field of config.searchFields) {
        let searchElement = document.getElementById("query_by_" + field)
        if (searchElement.checked) {
            // The seach operator, eg. "eq", "sw", etc
            const opElement = document.getElementById("search_operator_" + field)
            // The operator defaults to "in" for location searches, which do not have an operator field
            let op = "in"
            if (opElement != null) {
                op = opElement.value
            }
            // Case insensitivity is handled by adding a "i" to the operator
            const caseElem = document.getElementById("search_case_" + field)
            if (caseElem != null && caseElem.checked != true) {
                op += "i"
            }
            // Get the values being searched for. config.searchArgs holds the maximum
            // number allowed but some search terms will work with less
            let searchValues = new Array()
            for (let i=1; i<= config.searchArgs[field]; i++) {
                let valueElem = document.getElementById(`search_value_${field}_${i}`)
                if (valueElem != null && valueElem.value != "") {
                    searchValues.push(valueElem.value)
                }
            }
            // Special treatment for dates and timezones
            if (field == "obs_date") {
                searchValues = buildObsDateSearchValues(searchValues)
                // If we're searching on a date range, use "in" as the operator
                if (searchValues.length == 2) {
                    op = "in"
                }
                else {
                    op="eq"
                }
            }
            queryParams.set(field, {"operator": op, "values": searchValues})
        }
    }

    // Build query parameters for additional terms being filtered on. Currently only
    // "instrument" is supported.
    const instruments = document.querySelectorAll("input[id^='instrument_']")
    const instrumentValues = ["instrument"]
    for (const instrument of instruments) {
        if (instrument.checked) {
            /* Only send instruments that aren't "category" instruments to the backend*/
            if (config.instruments[instrument.value].category == false) {
                instrumentValues.push(instrument.value)
            }
        }
    }

    if (instrumentValues.length > 0) {
        queryParams.set("filters", instrumentValues)
    }


    const countRadioInput = document.getElementById("id_count_0")

    // Check for a query only returning the count
    if (countRadioInput.checked) {
        queryParams.set("count","")
    }
    else {
        // For non-count queries, read the result formatting options and pass them in the query parameters

        // Page size and coordinate format
        let page_size = document.getElementById("id_page_size").value
        if (page_size == "") {
            page_size =config.defaults["page_size"]
        }
        queryParams.set("page_size", page_size)
        queryParams.set("coord_format", document.getElementById("id_coord_format").value)

        // What fields to sort on
        let sortValue = document.getElementById("id_sort_fields").value
        if (document.getElementById("id_sort_dir").value=="-") {
            sortValue = "-" + sortValue
        }
        queryParams.set("sort", sortValue)

        // What results to return
        let selectedResults = document.querySelectorAll("input[id$='_result']")
        let results = []
        for (const result of selectedResults) {
            if (result.checked == true) {
                results.push(result.value)
            }
            /* Include the download link when getting the filename */
            if (result.value == "filename") {
                results.push("download_link")
            }
        }

        if (results.length == 0) {
            // Default results if none are selected
            results.push("filename")
            results.push("download_link")
            results.push("obs_date")
        }
        queryParams.set("results", results)
    }
    // What page to query for when paging through results.
    queryParams.set("page", page)
    return queryParams
}

// Convert the passed in date/time values to ISO dates with timezone for the backend.
function buildObsDateSearchValues(dateSearchValues) {
    // TODO better parsing/validation of date values
    if (dateSearchValues.length == 1) {
        // Lick time is noon-to-noon PST
        var startDate = new Date(dateSearchValues[0] + " 12:00:00-0800")
        // Get the end date by adding (almost) a day in ms
        let endEpochTime = startDate.getTime() + 86399999
        var endDate = new Date(endEpochTime)
    }
    else if (dateSearchValues.length == 2) {
        var startDate = new Date(dateSearchValues[0] + " 12:00:00-0800")
        var endDate = new Date(dateSearchValues[1] + " 12:00:00-0800")
        if (startDate == endDate) {
            // The same date was entered as both start and end time, so treat as if a single date were entered
            let endEpochTime = startDate.getTime() + 86399999
            endDate = new Date(endEpochTime)
        }
    }
    else {
        // For now let the backend validate and return an error
        return dateSearchValues
    }

    if (startDate.getTime() > endDate.getTime()) {
        // dates are swapped
        return [endDate.toISOString(), startDate.toISOString()]
    }
    else {
        return [startDate.toISOString(), endDate.toISOString()]
    }
}

// Convert a query parameter map to a (relative) URL
function queryParamsToString(queryParams) {
    /* I don't use urlSearchParams directly because I want to serialize lists with commas
       and I want to disinguish the operator from the values for indexed fields */
    const urlSearchParams = new URLSearchParams()

    for (const [key,value] of queryParams) {
        if (value instanceof Array) {
            urlSearchParams.append(key,value.join(","))
        }
        else if (value instanceof Object && "operator" in value) {
            urlSearchParams.append(key,`${value.operator},${value.values.join(",")}`)
        }
        else {
            urlSearchParams.append(key, value)
        }
    }
    return config.backendURLBase + "data/?" + urlSearchParams.toString()
}
/* Query Results section */
const downloadSelectedButtons = document.querySelectorAll("button[id^='download_selected'")
const downloadAllButtons = document.querySelectorAll("button[id^='download_all'")
const downloadButtons = Array.from(downloadSelectedButtons).concat(Array.from(downloadAllButtons))
const resultsTable = document.getElementById("search_results_table")
const resultsCountElems = document.querySelectorAll("span[id^='search_results_count'")
const pageControls = document.querySelectorAll("span[id^='search_results_page_controls'")
const searchResultsForm = document.getElementById("search_results_form")
const submitDownloadButton = document.getElementById("submit_download")
let resultHdrCheckbox = null
let resultCheckboxes = []
let numRowsSelected = 0
let latestQueryResults = null

document.addEventListener("DOMContentLoaded", initializeDownloadButtons)

function initializeDownloadButtons(event) {
     for (const button of downloadSelectedButtons) {
        button.addEventListener("click", downloadSelected)
    }
    for (const button of downloadAllButtons) {
        button.addEventListener("click", downloadAll)
    }
}

function processResults(queryParams, jsonResults) {
    if ("error" in jsonResults) {
        showResultsCountOnly(0)
        errorSection.showErrorMessage(jsonResults.error)
    }
    else {
        errorSection.clearErrorMessages()
        if (jsonResults.count == 0 || queryParams.has("count")) {
            // Only show the number of results from the query
            showResultsCountOnly(jsonResults.count)
        }
        else {
            // Save results for reference when downloading
            latestQueryResults = jsonResults.results

            // Show the results in a table
            showResults(queryParams,jsonResults)
        }
    }
}

function showResultsCountOnly(count) {
    // Hide the download buttons
    for (const button of downloadButtons) {
        button.hidden = true
    }
    // Hide the result table
    resultsTable.hidden=true
    for (const resultCountElem of resultsCountElems) {
        // Hide the counter footer, since it's redundant with the header when there's no results table
        if (resultCountElem.id == "search_results_count_footer") {
            resultCountElem.hidden=true
        }
        else {
            resultCountElem.textContent = `Number of results: ${count}`
        }
    }
    // Hide the page controls
    for (const pageControl of pageControls) {
        pageControl.hidden=true
    }
}

function showResults(queryParams, resultJson){

    /* Build the results table */
    const resultCols = getResultColsInDisplayOrder(queryParams)
    const headerRow = buildHeaderRow(resultCols,resultsTable,"search_results")
    const resultsBody = buildResultRows(resultCols, resultJson.results,resultsTable,"search_results")

    /* Show the table */
    resultsTable.hidden = false

    /* The download selected buttons are disabled until a row is selected */
    for (const button of downloadSelectedButtons) {
        button.disabled = true
        button.hidden=false
    }
    for (const button of downloadAllButtons) {
        button.hidden=false
    }

    /* Set # of results and show the counts for the result table's header and footer*/
    for (const resultCountElem of resultsCountElems) {
        /* Show the counter footer, since it's hidden when there's no results table */
        if (resultCountElem.id == "search_results_count_footer") {
            resultCountElem.hidden=false
        }
        resultCountElem.textContent = `Showing ${resultJson.results.length} of ${resultJson.count} results.`
    }

    // Build and show the page navigation controls
    for (const pageControl of pageControls) {
        buildPageControls(pageControl, queryParams,resultJson)
        pageControl.hidden = false
    }

}

/* Return the result column names in the order they should be displayed.
This allows for the front end to decide on consistent and hopefully
aesthetically nice column format.
*/
function getResultColsInDisplayOrder(queryParams) {
    const resultsInOrder = []

    // First get the columns with a configured order
    for (const field of config.resultFieldOrder) {
        if (queryParams.get("results").includes(field) ) {
            resultsInOrder.push(field)
        }
    }

    // Next add any result fields that don't have a configured order to the end
    // Note download_link is for internal use, not to be shown to users
    for (const field of queryParams.get("results")) {
        if (!config.resultFieldOrder.includes(field) && field != "download_link"){
            resultsInOrder.push(field)
        }
    }
    return resultsInOrder
}
function buildSelectCheckbox(id) {
    const inputElem = document.createElement("input")
    inputElem.type="checkbox"
    inputElem.id = id
    return inputElem
}
function buildHeaderRow(resultFields, tableElem, prefix) {
    /* Delete the old header first */
    tableElem.deleteTHead()
    const headerElem = tableElem.createTHead()
    const headerRowElem = headerElem.insertRow()

    /* First add the selection column with checkbox for selecting all/none of the results for download */
    let headerCell = document.createElement("th")
    headerCell.className = prefix + "_header" + " " + prefix + "_select"
    headerCell.scope = "col"
    headerCell.appendChild(new Text("Select All"))
    headerCell.appendChild(document.createElement("br"))
    resultHdrCheckbox = buildSelectCheckbox(prefix + "_hdr_select")
    headerCell.appendChild(resultHdrCheckbox)
    resultHdrCheckbox.addEventListener("click", selectResults)
    headerRowElem.appendChild(headerCell)

    /* Add columns for the result fields, in the order configured for aesthetics */
    for (const field of resultFields) {
        const headerCell = document.createElement("th")
        headerCell.className = prefix + "_header"
        headerCell.scope = "col"
        headerCell.appendChild(new Text(dataDictionary.resultFields[field].human_name))
        if (dataDictionary.resultFields[field].units != "") {
            headerCell.appendChild(document.createElement("br"))
            if (dataDictionary.resultFields[field].units == "angle") {
                /* TODO support coordinate formats */
                headerCell.appendChild(new Text("(Degrees)"))
            }
            /* All dates are displayed as UTC-8 */
            else if (dataDictionary.resultFields[field].units == "date") {
                headerCell.appendChild(new Text("(UTC-8)"))
            } else {
                headerCell.appendChild(new Text(`(${dataDictionary.resultFields[field].units})`))
            }
        }
        headerRowElem.appendChild(headerCell)
    }


    return headerRowElem
}


function buildResultRows(resultFields, results, tableElem, prefix) {
    /* Delete the old results first */
    const bodies = Array.from(tableElem.tBodies)
    for (const body of bodies) {
        tableElem.removeChild(body)
    }
    resultCheckboxes = []
    const bodyElem = tableElem.createTBody()

    for (let i=0; i < results.length; i++) {

        const rowElem = bodyElem.insertRow()

        /* First add the selection checkbox for selecting the row for download */
        let headerCell = document.createElement("td")
        headerCell.className = prefix + "_data" + " " + prefix + "_select"
        headerCell.scope = "col"
        const resultCheckbox = buildSelectCheckbox(prefix + `_select_${i}`)
        resultCheckboxes.push(resultCheckbox)
        headerCell.appendChild(resultCheckbox)
        resultCheckbox.addEventListener("click", rowSelected)
        rowElem.appendChild(headerCell)

        /* Add columns for the result fields, in the order configured for aesthetics */
        for (const field of resultFields) {
            headerCell = document.createElement("td")
            headerCell.className = prefix + "_data"
            headerCell.scope = "col"
            headerCell.appendChild(processSingleResult(results[i], field))
            rowElem.appendChild(headerCell)
        }
    }
    return bodyElem
}
function processSingleResult(result, field) {
    switch(field) {
        /* Convert filename to a link for downloading */
        case "filename":
            var anchorElem = document.createElement("a")
            anchorElem.href=result["download_link"]
            anchorElem.innerText = result[field]
            return anchorElem
        /* Convert header to a link for downloading */
        case "header":
            var anchorElem = document.createElement("a")
            anchorElem.href=result[field]
            anchorElem.innerText = "header"
            return anchorElem
        default:
            /* Convert dates from the server to UTC-8 per Lick Observatory standard */
            if (dataDictionary.resultFields[field].units == "date") {
                return new Text(dateStringToISOPST(result[field]))
            }
            else {
                return new Text(result[field])
            }
    }
}

function dateStringToISOPST(date){
    /* To get a date in an ISO format but in a specific timezone, I convert it to en-US format in that timezone and parse the result */
    const d = new Date(date)
    const formatterPST= Intl.DateTimeFormat("en-US", {"hour12":false,"year":"numeric","month":"2-digit","day":"2-digit","hour":"2-digit","minute":"2-digit","second":"2-digit","timeZone":"-08"})
    const usFormat = formatterPST.format(d)
    const [dateStr,timeStr] = usFormat.split(",")
    const [month,day,year] = dateStr.split("/")
    return `${year}-${month}-${day} ${timeStr.trim()}`
}


// Select/deselect result rows based on clicking the checkbox in the result table header
function selectResults(event) {
    // If the header checkbox is in the intermediate state, clicking it will
    // deselct all of the results
    if (event.target.indeterminate == true) {
        var value = false
        numRowsSelected = 0
    } else if (event.target.checked == true) {
        // If the header row checkbox is checked, select all of the results
        var value = true
        numRowsSelected = resultCheckboxes.length
    }
    else {
        // Otherwise the header row checkbox is unchecked, deselect all of the results
        var value = false
        numRowsSelected = 0
    }
    for (let i=0; i<resultCheckboxes.length; i++) {
        resultCheckboxes[i].checked=value
    }
    // Update the "Download Selected" buttons to be disabled if there are no rows selected.
    for (let i=0; i<downloadSelectedButtons.length; i++) {
        downloadSelectedButtons[i].disabled = (numRowsSelected == 0)
    }

}
// Event handler when a single result row is selected
function rowSelected(event) {

    // Update the "Download Selected" buttons based on how many rows are selected
    if (event.target.checked == true) {
        numRowsSelected++
    }
    else {
        numRowsSelected--
    }
    if (numRowsSelected < 0) {
        numRowsSelected = 0
    } else if (numRowsSelected > resultCheckboxes.length) {
        numRowsSelected = resultCheckboxes.length
    }
    for (let i=0; i<downloadSelectedButtons.length; i++) {
        downloadSelectedButtons[i].disabled = (numRowsSelected == 0)
    }
    // Update the header row check box to be unchecked if no rows are checked,
    // indeterminate if some rows are checked, or
    // checked if all rows are checked
    if (numRowsSelected == 0) {
        resultHdrCheckbox.checked = false
        resultHdrCheckbox.indeterminate = false
    } else if (numRowsSelected == resultCheckboxes.length) {
        resultHdrCheckbox.checked = true
        resultHdrCheckbox.indeterminate = false
    }
    else {
        resultHdrCheckbox.checked = false
        resultHdrCheckbox.indeterminate = true
    }
}


function buildPageControls(controlElem, queryParams, jsonResults) {
    /* Build the page navigation controls. These consist of a previous page control,
    one or more page buttons, possibily separated by ellipses, and a next page control.
    For example:
    < 1 ... 4 5 6 7 8 9 ... 16 >
    */

    /* Delete the old controls first */
    const old_controls = Array.from(controlElem.childNodes)
    for (const control of old_controls) {
        controlElem.removeChild(control)
    }

    // Figure out the total pages and next/previous page
    const totalPages = Math.ceil(jsonResults.count / queryParams.get("page_size"))
    const currentPage = Number(queryParams.get("page"))
    let prevPageValue = currentPage - 1
    let nextPageValue = currentPage + 1
    if (prevPageValue < 1 || jsonResults.previous == null) {
        // The previous page is invalid, so the control should be disabled
        prevPageValue = null
    }
    if (prevPageValue > totalPages || jsonResults.next == null) {
        // The next page is invalid, so the control should be disabled
        nextPageValue = null
    }

    // Add the previous page button
    controlElem.appendChild(buildPageButton("<", prevPageValue, jsonResults.previous))
    for (const page of determinePages(Number(queryParams.get("page")), totalPages, 10, 2)) {

        let pageURL = null
        if (page == "...") {
            controlElem.appendChild(new Text("\u2026"))
        }
        else if (page == currentPage) {
            controlElem.appendChild(buildPageButton(page, null, pageURL))
        }
        else {
            // Determine the URL by creating a copy of the original query params
            controlElem.appendChild(buildPageButton(page, page, pageURL))
        }
    }
    // The next page button
    controlElem.appendChild(buildPageButton(">", nextPageValue, jsonResults.next))

}

function buildPageButton(buttonText, pageValue) {
    // Build each page button such that it submits the query to the corect page
    const button = document.createElement("button")
    button.type="button"
    if (pageValue == null) {
        button.disabled = true
    }
    else {
        button.value = pageValue
        button.addEventListener("click",submitQuery)
    }
    button.textContent = buttonText
    return button
}

function determinePages(currentPage, totalPages, maxControls, surroundingControls) {
    /* Figures out what papge controls are needed for page navigation */


    // The page list always starts 1.
    let pageList = ["1"]

    // Set the start/end of page number iteration as if all pages will fit within the maximum number of controls
    let startRange = 2
    let endRange = totalPages
    let needStartEllipses = false
    let needEndEllipses = false

    if (totalPages > maxControls + 2) {
        /* All of the page numbers with the previous/next controls won't fit within the desired number of controls;
           some ellipses will be needed.

           At low pages numbers the ellipses will be before the last page.
           For example with max_controls = 12, total_pages=100, current_page = 2, surrounding = 2
               <<  1 <2> 3  4  5  6  7  8  ...100 >>
           This will continue to be the case until there aren't enough controls to hold the surrounding pages. This is the change over
           point. In this example the change over is between pages 6 and 7
               <<  1  2  3  4  5 <6> 7  8  ...100 >>
               <<  1 ... 4  5  6 <7> 8  9  ...100 >>

           To find the change over point, find the last page that could be displayed without elipses after the 1 (max_controls -2)
           and subtract the number of surrounding pages. The 2 includes the last page control and the ellipses before the last page.
        */
        let changeOver = maxControls - (2+surroundingControls)

        if (currentPage <= changeOver) {
            // The current page is before the change over, only one ellipses is needed, at the end
            needEndEllipses = true
            startRange = 2
            endRange = maxControls - 2
        } else {
            // After the change over, there will be one ellipses at the start, and potentially one at the end
            needStartEllipses = true

            if (currentPage + surroundingControls < totalPages) {
                // The current page is far enough away from the last page to require ellipses at the end
                needEndEllipses = true

                //  End the range with the last of the surrounding pages around the current_page
                endRange = currentPage + surroundingControls

                // Start the range with enough pages to fill up the maximum number of controls
                // (-4 to exclude for the two ellipses, and first and last page)
                startRange = (endRange-(maxControls-4))+1
            } else {
                // The current page is close enough to the final page that no ellipses are needed at the end
                // End the range just before the final page
                endRange = totalPages
                // Start the range with enough pages to fill up the maximum allowed controls (-3 for one ellipses,
                // and the first and last page)
                startRange=(endRange-(maxControls-3))+1
            }
        }
    }

    if (needStartEllipses) {
        pageList.push("...")
    }

    // Add the pages up to the end ellipses (if any)
    for (let i=startRange; i<=endRange; i++) {
        pageList.push(String(i))
    }

    if (needEndEllipses) {
        pageList.push("...")
        pageList.push(String(totalPages))
    }
    return pageList
}

function downloadSelected(event) {
    // Download selected was pressed. Build a list of files to download based on what's selected
    const filenamesToDownload = []
    for (const checkbox of resultCheckboxes) {
        if (checkbox.checked == true) {
            const id_parts = checkbox.id.split("_")
            const idx = id_parts[id_parts.length - 1]
            filenamesToDownload.push(latestQueryResults[idx].filename)
        }
    }

    submitDownload(filenamesToDownload)
}

async function downloadAll(event) {
    /* Download all was pressed. Build a list of files to download by re-runing our
    query to get all of the results. */
    const filenamesToDownload = []
    try {
        const queryParams = buildQueryParams(1)
        // Udate the QueryParams to only return filenames and to have a larger page size */
        queryParams.set("page_size", 1000)
        queryParams.set("results", ["filename"])
        let queryURL = queryParamsToString(queryParams)

        // Loop through all the result pages
        do {
            var results = await archiveClient.runQuery(queryURL)
            if ("error" in results && results["error"] !=null) {
                errorSection.showErrorMessage(results["error"])
                return
            } else {
                queryURL = results["next"]
                for (const result of results["results"]) {
                    filenamesToDownload.push(result["filename"])
                }
            }
        }
        while (queryURL != null)
    }
    catch (error) {
        errorSection.showErrorMessage(error.message)
        return
    }
    submitDownload(filenamesToDownload)

}

function submitDownload(filenamesToDownload) {
    console.log(`Num files to download ${filenamesToDownload.length}`)
    // Set up the download form with the filenames and (if needed) a csrf token
    if (filenamesToDownload.length == 0) {
        // Don't bother to submit an empty list
        return
    }
    searchResultsForm.download_files.value=JSON.stringify(filenamesToDownload)
    if (archiveClient.apiCSRFToken != null) {
        searchResultsForm.csrfmiddlewaretoken.value=archiveClient.apiCSRFToken
    }
    else {
        searchResultsForm.csrfmiddlewaretoken.value=""
    }
    submitDownloadButton.click()
}
