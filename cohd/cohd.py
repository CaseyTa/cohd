u"""
Columbia Open Health Data (COHD) API

implemented in Flask

@author: Joseph D. Romano
@author: Rami Vanguri
@author: Choonhan Youn
@author: Casey Ta

(c) 2017 Tatonetti Lab
"""

from flask import Flask, request, redirect, jsonify
from flask_cors import CORS
import query_cohd_mysql
import requests

#########
# INITS #
#########

app = Flask(__name__)
CORS(app)
app.config.from_pyfile(u'cohd_flask.conf')

##########
# ROUTES #
##########


@app.route(u'/')
def api_cohd():
    google_analytics(endpoint=u'/')
    return redirect("http://smart-api.info/ui/?url=/api/metadata/6c33ed14d628a982c79fa36a75dbbbcf", code=302)


@app.route(u'/api/omop/findConceptIDs')
@app.route(u'/api/v1/omop/findConceptIDs')
def api_omop_reference():
    return api_call(u'omop', u'findConceptIDs')


@app.route(u'/api/omop/concepts')
@app.route(u'/api/v1/omop/concepts')
def api_omop_concepts():
    return api_call(u'omop', u'concepts')


@app.route(u'/api/omop/mapToStandardConceptID')
def api_omop_mapToStandardConceptID():
    return api_call(u'omop', u'mapToStandardConceptID')


@app.route(u'/api/omop/mapFromStandardConceptID')
def api_omop_mapFromStandardConceptID():
    return api_call(u'omop', u'mapFromStandardConceptID')


@app.route(u'/api/omop/vocabularies')
def api_omop_vocabularies():
    return api_call(u'omop', u'vocabularies')


@app.route(u'/api/omop/xrefToOMOP')
def api_omop_xrefToOMOP():
    return api_call(u'omop', u'xrefToOMOP')


@app.route(u'/api/omop/xrefFromOMOP')
def api_omop_xrefFromOMOP():
    return api_call(u'omop', u'xrefFromOMOP')


@app.route(u'/api/metadata/datasets')
def api_metadata_datasets():
    return api_call(u'metadata', u'datasets')


@app.route(u'/api/metadata/domainCounts')
def api_metadata_domainCounts():
    return api_call(u'metadata', u'domainCounts')


@app.route(u'/api/metadata/domainPairCounts')
def api_metadata_domainPairCounts():
    return api_call(u'metadata', u'domainPairCounts')


@app.route(u'/api/metadata/patientCount')
def api_metadata_patientCount():
    return api_call(u'metadata', u'patientCount')


@app.route(u'/api/frequencies/singleConceptFreq')
@app.route(u'/api/v1/frequencies/singleConceptFreq')
def api_frequencies_singleConceptFreq():
    return api_call(u'frequencies', u'singleConceptFreq')


@app.route(u'/api/frequencies/pairedConceptFreq')
@app.route(u'/api/v1/frequencies/pairedConceptFreq')
def api_frequencies_pairedConceptFreq():
    return api_call(u'frequencies', u'pairedConceptFreq')


@app.route(u'/api/frequencies/associatedConceptFreq')
@app.route(u'/api/v1/frequencies/associatedConceptFreq')
def api_frequencies_associatedConceptFreq():
    return api_call(u'frequencies', u'associatedConceptFreq')


@app.route(u'/api/frequencies/associatedConceptDomainFreq')
@app.route(u'/api/v1/frequencies/associatedConceptDomainFreq')
def api_frequencies_associatedConceptDomainFreq():
    return api_call(u'frequencies', u'associatedConceptDomainFreq')


@app.route(u'/api/frequencies/mostFrequentConcepts')
@app.route(u'/api/v1/frequencies/mostFrequentConcepts')
def api_frequencies_mostFrequentConcept():
    return api_call(u'frequencies', u'mostFrequentConcepts')


@app.route(u'/api/association/chiSquare')
def api_association_chiSquare():
    return api_call(u'association', u'chiSquare')


@app.route(u'/api/association/obsExpRatio')
def api_association_obsExpRatio():
    return api_call(u'association', u'obsExpRatio')


@app.route(u'/api/association/relativeFrequency')
def api_association_relativeFrequency():
    return api_call(u'association', u'relativeFrequency')


# Retrieves the desired arg_names from args and stores them in the queries dictionary. Returns None if any of arg_names
# are missing
def args_to_query(args, arg_names):
    query = {}
    for arg_name in arg_names:
        arg_value = args[arg_name]
        if arg_value is None or arg_value == [u'']:
            return None
        query[arg_name] = arg_value
    return query


def google_analytics(endpoint=None, service=None, meta=None):
    """ Reports the endpoint to Google Analytics

    Reports the endpoint as a pageview to Google Analytics. If endpoint is specified, then endpoint is reported.
    Otherwise, if service and meta are specified, then /api/{service}/{meta} is reported.

    Uses Google Analytics Measurement Protocol for reporting:
    https://developers.google.com/analytics/devguides/collection/protocol/v1/devguide

    :param endpoint: The endpoint to submit as the document page
    :param service: Combine with meta to submit /api/{service}/{meta} as the document page.
    :param meta: Combine with service to submit /api/{service}/{meta} as the document page.
    :return: None
    """
    print request.remote_addr
    print request.user_agent

    # Report to Google Analytics iff the tracking ID is specified in the configuration file
    if u'GA_TID' not in app.config:
        # Google analytics not configured. Exit.
        return

    # Report the endpoint if specified, otherwise /api/{service}/{meta}
    if endpoint is None:
        if service is None or meta is None:
            # Insufficient information.
            print 'Insufficient endpoint information for cohd.py::google_analytics'
            return

        endpoint = u'/api/{service}/{meta}'.format(service=service, meta=meta)

    try:
        # Use a small timeout so that the Google Analytics request does not cause delays if there is an issue
        endpoint_ga = u'http://www.google-analytics.com/collect'
        payload = {
            u'v': 1,
            u'tid': app.config[u'GA_TID'],
            u'cid': 555,
            u't': u'pageview',
            u'dh': u'cohd.nsides.io',
            u'dp': endpoint,
            u'uip': request.remote_addr,
            u'ua': request.user_agent
        }
        requests.post(endpoint_ga, data=payload, timeout=0.1)
    except requests.exceptions.Timeout:
        # Log the timeout
        print 'Google Analytics timeout: ' + endpoint


@app.route(u'/api/query')
@app.route(u'/api/v1/query')
def api_call(service=None, meta=None, query=None):
    if service is None:
        service = request.args.get(u'service')
    if meta is None:
        meta = request.args.get(u'meta')

    print u"Service: ", service
    print u"Meta/Method: ", meta

    if service == [u''] or service is None:
        result = u'No service selected', 400
    elif service == u'metadata':
        if meta == u'datasets' or \
                meta == u'domainCounts' or \
                meta == u'domainPairCounts' or \
                meta == u'patientCount':
            result = query_cohd_mysql.query_db(service, meta, request.args)
        else:
            result = u'meta not recognized', 400
    elif service == u'omop':
        if meta == u'findConceptIDs' or \
                meta == u'concepts' or \
                meta == u'mapToStandardConceptID' or \
                meta == u'mapFromStandardConceptID' or \
                meta == u'vocabularies' or \
                meta == u'xrefToOMOP' or \
                meta == u'xrefFromOMOP':
            result = query_cohd_mysql.query_db(service, meta, request.args)
        else:
            result = u'meta not recognized', 400
    elif service == u'frequencies':
        if meta == u'singleConceptFreq' or \
                meta == u'pairedConceptFreq' or \
                meta == u'associatedConceptFreq' or \
                meta == u'mostFrequentConcepts' or \
                meta == u'associatedConceptDomainFreq':
            result = query_cohd_mysql.query_db(service, meta, request.args)
        else:
            result = u'meta not recognized', 400
    elif service == u'association':
        if meta == u'chiSquare' or \
                meta == u'obsExpRatio' or \
                meta == u'relativeFrequency':
            result = query_cohd_mysql.query_db(service, meta, request.args)
        else:
            result = u'meta not recognized', 400
    else:
        result = u'service not recognized', 400

    # Report the API call to Google Analytics
    google_analytics(service=service, meta=meta)

    return result


if __name__ == u"__main__":
    app.run(host=u'localhost')
