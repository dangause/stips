Manual Frontend Test Procedure
==============================

This test procedure is intended to provide basic validation of the lick archive's functionality,
with an emphasis on frontend UI features that are difficult to test in an automated fashion.
From time to time, it should be run against the archive in different browsers and different
operating systems to verify cross platform compatibility.

1. Remove all cookies and site data from ucolick.org.

2. Navigate to https://archive.ucolick.org/.

    * Verify that the website comes up, and is in its "light" mode theme.
    * Verify the "Search By" options are unchecked and grayed out.
    * Verify no user is logged in.
    * Verify All of the instruments are checked.
    * Verify that "Return information about matching files." is selected
    * Verify the correct defaults in the Result Format section
    * Verify "Return only a acount of matching files is grayed out."
    * Verify the Seaarch results simply shows "Number of results: 0"
    * Verify the side bar shows "Search the repository" as the current page.
    * Verify the "Browse the repository" by date. Goes to the old repository.
    * Verify the "Mt Hamilton Home Page" link works.
    * Verify the UC Observatory Home Page link works.

3. Click the "Switch to Dark Theme" button
    * Verify the theme changes.

4. Click the "How to use the repository" button.
    * Verify the link works.
    * Verify the theme stays the same

5. Click the "Switch to Light Theme" button
    * Verify the theme changes

6. Click the "Description of all fields" link.
    * Verify it works
    * Verify the theme stays the same (light mode)

7. Click Search the repository
    * Verify the link works

8. Click each "Search by" option on and off.
    * Verify controls are disabled/enabled when they are off/on

9. Click "Switch to Dark Theme". Repeat step 8
    * Verify controls disabled/enabled look correct in the dark theme.

10. Check Observation date. Change the operator to "between". Enter the dates 2019-05-23 and 2019-05-31
    * Verify the second observation date text field becomes visible and is enabled.

11. Check Path and Filename. Change the operator to "starts with" enter 2019-05/23/.

12. Click the "Kast" checkbox off. Then check it on again.
    * Verify both Kast Blue and Kast Red are toggled

13. Click on the "Deslect All" button.
    * Verify all of the instrument checkboxes uncheck

14. Click the "Kast Blue" checkbox. Then click the "Kast Red" checkbox
    * Verify the "Kast Blue" and "Kast Red" checkboxes work.
    * Verify the "Kast" checkbox becomes checked once both "Kast Blue" and "Kast Red" are checked

15. Click "Shane AO/ShARCS"
    * Verify "Shane AO/ShARCS" is checked

16. Click "Select All"
    * Verify all  instrument checkboxes are checked.

17. Change "Results / page" to 10, press Tab
    * Verify the change
    * Verify that the "RA/DEC format" pulldown is selected

18. Press tab to cycle through the result fields. Press "space" when "File size" is highlighted.
    * Verify that tab properly cycles thorugh all the controls and result fields.
    * Verify "File size" is highlighted when "space" is clicked

19. Press tab to cycle through the rest of the Result fields.
    * Verify they are highlighted in sequence

20. Click "Date file becomes public" in the result fields.
    * Verify the field is highlighted.

21. Check "Return only a count of matching files".
    * Verify controls in the above section are disabled.

22. Click Submit Query
    * Verify a count of 68 results is returned.

23. Click "Return information about matching files".
    * Verify the result fields are enabled again.
    * Verify the previous settings are remembered

24. Submit Query
    * Verify the result table is shown with 7 pages, 10 in this page.
    * Verify both "Download Selected" buttons are disabled
    * Verify both "Download All" buttons are enabled.
    * Verify the "1" page buttons are disabled.
    * Verify the "2" through "7" page buttons are enabled.
    * Verify the "<" buttons are disabled.
    * Verify the ">" buttons are enabled.

25. Check/uncheck select all
    * Verify all results on the page are checked/unchecked.
    * Verify "Download Selected" is enabled when the results are checked

26. Check each individual row in the results page.
    * Verify the "Select All" checkbox shows the "-" intermediate state once one is checked.
    * Verify "Download Selected" is enabled once one is checked.
    * Verify the "Select All" checkbox shows as checked once all rows are checked.

27. Click the top "Download Selected" button
    * Verify a ``data-2019-05-23-shane.tar.gz`` file is downloaded.
    * Verify it is about 11MiB in size and contains the 10 files in the first page.
    * Delete the file when done

28. Repeat step 27 but using the bottom "Download Selected" button.

29. Click the filename for the first result on the page.
    * Verify it is downloaded and has the correct size.
    * Delete the file when done.

30. Click top "Download All" button.
    * Verify a ``data-2019-05-23-shane.tar.gz`` file is downloaded.
    * Verify it is about 97 MiB in size and contains 68 files.
    * Delete the file when done.

31. Repeat step 30 but for the bottom "Download All" button.

32. Middle click the "header" linker for the first result row.
    * Verify the header comes up in a new tab.

33. Click the ">" next page button at the top of the results table to cycle through all 7 pages.
    * Verify that as the page changes, the current page buttons are disabled while the other page buttons are enabled.
    * Verify the "<" previous page button is enabled once past page 1.
    * Verify the ">" button is disabled upon reaching the last page.

34. Click the "<" previous page button at the top of the results table to cycle through all 7 pages.
    * Verify that as the page changes, the current page buttons are disabled while the other page buttons are enabled.
    * Verify the ">" previous page button is enabled once past page 7.
    * Verify the "<" button is disabled upon reaching page 1.

35. Click numbered "page" button at the top of the results table to cycle through each page in the results.
    * Verify that as the page changes, the current page buttons are disabled while the other page buttons are enabled.
    * Verify the ">" previous page button is disabled on page 7.
    * Verify the "<" button is disabled on page 1.

36. Repeat steps 33 through 35 with the page control buttons at the bottom of the results table.

37. The web page should be in the "Dark" theme. If it is not click "Switch to Dark Theme" to switch to that theme.
    Once on that page close the web page and browser window.

38. Open the browser again and navigate to "https://archive.ucolick.org/". Verify the "Dark Theme" is still active.

39. Click the "Login" button. Click the "Switch to light theme" button.
    * Verify the page opens
    * Verify the theme changes

40. Enter an invalid username/password, and press "enter"
    * Vertify the login fails

41. Click the "Return to search page" link.
    * Verify the browser is sent to the "Search the repository" page

42. Enter a valid username/password and click the login button.
    * Verify user is sent back to the "Search the repository" page
    * Verify the user is displayed in the upper right hand corner.

43. Click the "How to use the repository" link.
    * Verify the user is still in the upper right hand corner.

44. Click the "Description of all fields" link.
    * Verify the user is still in the upper right hand corner.

45. Click the "Search the repository" link.
    * Verify the user is still in the upper right hand corner.

46. Click the "Logout" button.
    * Verify the upper right says "You are not logged in"

47. Click the "Login" button.
    * Verify the  upper right says "You are not logged in"

48. Click the "How to use the repository" link.
    * Verify the  upper right says "You are not logged in"

49. Click the "Description of all fields" link.
    * Verify the  upper right says "You are not logged in"
