#!/usr/bin/python3
# -*- coding: utf-8 -*-
import argparse
import csv
import json
import sys

import requests
from sortedcontainers import SortedSet

FIELD_NAME = 'field_name'
EXISTING = 'existing'
EXISTING_PERCENTAGE = 'existing_percentage'
NOTEXISTING = 'notexisting'
NOTEXISTING_PERCENTAGE = 'notexisting_percentage'

USED_FIELDS_DELIMITER = ','

HTTP_PREFIX = 'http'


def get_header():
    return [FIELD_NAME,
            EXISTING,
            EXISTING_PERCENTAGE,
            NOTEXISTING,
            NOTEXISTING_PERCENTAGE]


def format_solr_instance(host, port):
    formatted_host = host
    if not str(host).startswith(HTTP_PREFIX):
        formatted_host = "{:s}://{:s}".format(HTTP_PREFIX, host)
    if port:
        return "{:s}:{:d}/solr/".format(formatted_host, port)
    return "{:s}/solr/".format(formatted_host)


def solr_request(core, base_uri, request):
    response = requests.get(request, timeout=60)
    if response.status_code != 200:
        content = None
        if response.content:
            content = response.content.decode('utf-8')
        raise RuntimeError(
            'Solr core "%s" at solr instance "%s" is not available, i.e. could not execute request to "%s" successfully; got a "%d" ("%s")' % (
            core, base_uri, request, response.status_code, content))
    response_body = response.content.decode('utf-8')
    return response_body


def solr_request_json(request, base_uri, core):
    return json.loads(solr_request(core, base_uri, request))


def get_schema_fields(base_uri, core):
    schema_request = "{:s}{:s}/schema?wt=json".format(base_uri, core)

    schema = solr_request_json(schema_request, base_uri, core)

    if "schema" not in schema or "fields" not in schema['schema']:
        raise RuntimeError('something went wrong, while requesting the schema from "%s", got response "%s"' % (
            schema_request, schema))

    fields = schema['schema']['fields']

    return [(field['name']) for field in fields]


def get_used_fields(base_uri, core):
    used_fields_request = "{:s}{:s}/select?q=*%3A*&wt=csv&rows=0".format(base_uri, core)

    used_fields_response = solr_request(core, base_uri, used_fields_request)

    lines = used_fields_response.splitlines()

    if len(lines) != 1:
        raise RuntimeError('something went wrong, while requesting the used fields from "%s", got response "%s"' % (
            used_fields_request, used_fields_response))

    used_fields = lines[0]

    return used_fields.split(USED_FIELDS_DELIMITER)


def get_fields(base_uri, core):
    schema_fields = get_schema_fields(base_uri, core)
    used_fields = get_used_fields(base_uri, core)
    fields = schema_fields + used_fields

    return SortedSet(set(fields))


def get_records_total(base_uri, core):
    total_request = "{:s}{:s}/select?q=*%3A*&rows=0&wt=json".format(base_uri, core)

    response_json = solr_request_json(total_request, base_uri, core)

    if "response" not in response_json or "numFound" not in response_json['response']:
        raise RuntimeError(
            'something went wrong, while requesting the total number of records from "%s", got response "%s"' % (
                total_request, response_json))

    return response_json['response']['numFound']


def get_field_total(field, base_uri, core):
    total_request = "{:s}{:s}/select?q={:s}%3A*&rows=0&wt=json".format(base_uri, core, field)

    response_json = solr_request_json(total_request, base_uri, core)

    if "response" not in response_json or "numFound" not in response_json['response']:
        raise RuntimeError(
            'something went wrong, while requesting the total number field "%s" existing in the records from "%s", got response "%s"' % (
                field, total_request, response_json))

    return response_json['response']['numFound']


def get_field_statistics(field, base_uri, core, records_total):
    field_total = get_field_total(field, base_uri, core)
    field_total_percentage = (float(field_total) / float(records_total)) * 100

    return (field_total,
            "{0:.2f}".format(field_total_percentage))


def get_all_field_statistics(field, base_uri, core, records_total):
    field_stats = get_field_statistics(field, base_uri, core, records_total)
    field_neg_stats = get_field_statistics("-{:s}".format(field), base_uri, core, records_total)

    return {FIELD_NAME: field,
            EXISTING: field_stats[0],
            EXISTING_PERCENTAGE: field_stats[1],
            NOTEXISTING: field_neg_stats[0],
            NOTEXISTING_PERCENTAGE: field_neg_stats[1]}


def csv_print(field_statistics):
    header = get_header()
    with sys.stdout as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header, dialect='unix')

        writer.writeheader()
        for field_statistic in field_statistics:
            writer.writerow(field_statistic)


def run():
    parser = argparse.ArgumentParser(prog='solr-fstats',
                                     description='returns field statistics of a Solr index; prints the output as pure CSV data (all values are quoted) to stdout',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    optional_arguments = parser._action_groups.pop()

    required_arguments = parser.add_argument_group('required arguments')
    required_arguments.add_argument('-core', type=str, help='Solr core to use', required=True)

    optional_arguments.add_argument('-host', type=str, default='localhost',
                                    help='hostname or IP address of the Solr instance to use')
    optional_arguments.add_argument('-port', type=int, help='port of the Solr instance to use')

    parser._action_groups.append(optional_arguments)

    args = parser.parse_args()
    solr_instance = format_solr_instance(args.host, args.port)

    fields = get_fields(solr_instance, args.core)
    total = get_records_total(solr_instance, args.core)

    stats = [(get_all_field_statistics(field, solr_instance, args.core, total)) for field in fields]

    csv_print(stats)


if __name__ == "__main__":
    run()
