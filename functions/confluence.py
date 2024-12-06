import pandas as pd
import datetime
from datetime import datetime
from atlassian import Confluence
import json


def bulletpointer(data):
    back = "<ul>"
    for x in data:
        back += f"<li>{x}</li>"
    back += "</ul>"
    return back


def convert_to_html_table(data=None, escape=True, transpose_table=False):
    df = pd.DataFrame(data)
    if transpose_table:
        html_table = df.T.to_html(index=False, escape=escape)
    else:
        html_table = df.to_html(index=False, escape=escape)
    return html_table


def confluence_update_page(
    title=None,
    parent_id=None,
    table=None,
    representation="storage",
    full_width=False,
    confluence=None,
    body_header=None,
    body_footer=None,
    escape_table=True,
    transpose_table=False,
    toc=False,
):

    if toc:
        body = '<ac:structured-macro ac:name="toc"/>'
    else:
        body = ""

    if body_header:
        body += body_header
    if confluence and title and parent_id:
        children = confluence.get_page_child_by_type(parent_id, type="page")
        confluence_page_id = None
        for child in children:
            if child["title"] == title:
                confluence_page_id = child["id"]
        if table:
            table = convert_to_html_table(
                data=table, escape=escape_table, transpose_table=transpose_table
            )
            body += table
        if body_footer:
            body += body_footer
        if confluence_page_id:
            confluence.update_page(
                confluence_page_id,
                title,
                body,
                parent_id=parent_id,
                representation=representation,
                full_width=full_width,
                minor_edit=True,
            )
        else:
            confluence.update_or_create(
                parent_id,
                title,
                body,
                representation=representation,
                full_width=full_width,
            )
    else:
        print("Missing confluence parameters")
        print("title:", title)
        print("parent_id:", parent_id)
        print("information:", table)
        print("confluence:", confluence)
        return False


def style_text(text, bold=False, italic=False, underline=False, color=None, h=None):
    if color and (color.lower() == "good" or color.lower() == "green"):
        text = f'<span style="color: rgb(4, 138, 26);">{text}</span>'
    if color and (color.lower() == "bad" or color.lower() == "red"):
        text = f'<span style="color: rgb(207, 12, 12);">{text}</span>'
    if color and color.lower() == "yellow":
        text = f'<span style="color: rgb(235, 232, 52);">{text}</span>'
    if color and color.lower() == "orange":
        text = f'<span style="color: rgb(201, 149, 26);">{text}</span>'
    if bold:
        text = f"<strong>{text}</strong>"
    if h:
        text = f"<h{h}>{text}</h{h}>"
    return text


def cleanup_children(
    confluence_url, confluence_token, confluence_page_id, sub_page_name=None
):
    confluence = Confluence(url=confluence_url, token=confluence_token)
    if sub_page_name:
        children = confluence.get_page_child_by_type(confluence_page_id, type="page")
        for child in children:
            if child["title"] == sub_page_name:
                confluence_page_id = child["id"]
    children = confluence.get_page_child_by_type(confluence_page_id, type="page")
    for child in children:
        print(f"Removing {child['title']}")
        confluence.remove_page(child["id"], status=None, recursive=False)


def get_childid(confluence=None, confluence_page_id=None, sub_page_name=None):
    children = confluence.get_page_child_by_type(confluence_page_id, type="page")
    for child in children:
        if child["title"] == sub_page_name:
            return child["id"]
    return None


def get_tables(confluence=None, confluence_page_id=None):
    tables = confluence.get_tables_from_page(confluence_page_id)
    return json.loads(tables)
