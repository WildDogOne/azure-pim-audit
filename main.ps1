# Define file paths
$groupCsv = "data/exportGroup_2024-8-30.csv"
$roleCsv = "data/Roleassignments.csv"
$outputCsv = "data/RoleAssignmentsWithUsers.csv"
Connect-MgGraph -Scopes "Group.ReadWrite.All"

# Read the group CSV file and create a dictionary
$groupDict = @{}
# Get all groups from Microsoft Graph
$groups = Get-MgGroup -All
# Populate the dictionary with group display names and IDs
foreach ($group in $groups) {
    $groupDict[$group.DisplayName] = $group.Id
}

##Import-Csv -Path $groupCsv -Encoding UTF8 | ForEach-Object {
##    $groupDict[$_.displayName] = $_.id
##}

# Create an array to hold the output data
$outputArray = @()

# Read the role CSV file and create an array of roles
Import-Csv -Path $roleCsv -Encoding UTF8 | ForEach-Object {
    if ($groupDict.ContainsKey($_."User Group Name") -and $_."Assignment State" -eq "Eligible") {
        Write-Host "Getting members for GroupID: $($groupDict[$_."User Group Name"]) - GroupName: $($_."User Group Name")"
        $members = Get-MgGroupMember -GroupId $groupDict[$_."User Group Name"] | Select-Object * -ExpandProperty additionalProperties | Select-Object {$_.AdditionalProperties["userPrincipalName"]}, {$_.AdditionalProperties["displayName"]}
        foreach ($member in $members) {
            write-host $member.'$_.AdditionalProperties["userPrincipalName"]'
            $outputArray += [PSCustomObject]@{
                "User Group Name" = $_."User Group Name"
                "Role Name" = $_."Role Name"
                "User Principal Name" = $member.'$_.AdditionalProperties["userPrincipalName"]'
                "Display Name" = $member.'$_.AdditionalProperties["displayName"]'
            }
        }
    }
    elseif ($_."Assignment State" -eq "Eligible") {
        $outputArray += [PSCustomObject]@{
            "User Group Name"     = "N/A"
            "Role Name"           = $_."Role Name"
            "User Principal Name" = $_."User Group Name"
            "Display Name" = "N/A"
        }
    }
}

# Export the output array to a new CSV file
$outputArray | Export-Csv -Path $outputCsv -NoTypeInformation -Encoding UTF8

Write-Host "Output written to $outputCsv"