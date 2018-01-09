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
    return redirect("http://smart-api.info/ui/?url=/api/metadata/6c33ed14d628a982c79fa36a75dbbbcf")


@app.route(u'/api/v1/omop/findConceptIDs')
def api_omop_reference():
    return api_call(u'omop', u'findConceptIDs')


@app.route(u'/api/v1/omop/concepts')
def api_omop_concepts():
    return api_call(u'omop', u'concepts')


@app.route(u'/api/v1/frequencies/singleConceptFreq')
def api_frequencies_singleConceptFreq():
    return api_call(u'frequencies', u'singleConceptFreq')


@app.route(u'/api/v1/frequencies/pairedConceptFreq')
def api_frequencies_pairedConceptFreq():
    return api_call(u'frequencies', u'pairedConceptFreq')


@app.route(u'/api/v1/frequencies/associatedConceptFreq')
def api_frequencies_associatedConceptFreq():
    return api_call(u'frequencies', u'associatedConceptFreq')


@app.route(u'/api/v1/frequencies/associatedConceptDomainFreq')
def api_frequencies_associatedConceptDomainFreq():
    return api_call(u'frequencies', u'associatedConceptDomainFreq')


@app.route(u'/api/v1/frequencies/mostFrequentConcepts')
def api_frequencies_mostFrequentConcept():
    return api_call(u'frequencies', u'mostFrequentConcepts')


@app.route(u'/api/v1/query')
def api_call(service=None, meta=None, query=None):
    if service is None:
        service = request.args.get(u'service')
    if meta is None:
        meta = request.args.get(u'meta')
    if query is None:
        query = request.args.get(u'q')

    print u"Service: ", service
    print u"Meta/Method: ", meta
    print u"Query: ", query

    if service == [u''] or service is None:
        response.status = 400
        return u'No service selected'
    elif len(service) == 1:
        json_result = jsonify({u"results": []})

    # MySQL
    elif service == u'omop':
        if meta == u'findConceptIDs' or meta == u'concepts':
            json_result = query_cohd_mysql.query_db(service, meta, query)
    elif service == u'frequencies':
        if meta == u'singleConceptFreq' or meta == u'pairedConceptFreq' or meta == u'associatedConceptFreq' or meta == u'mostFrequentConcepts':
            json_result = query_cohd_mysql.query_db(service, meta, query)
        elif meta == u'associatedConceptDomainFreq':
            concept_id = request.args.get(u'concept_id')
            domain_id = request.args.get(u'domain')

            if concept_id is None or concept_id == [u'']:
                response.status = 400
                return u'No concept_id selected'

            if domain_id is None or domain_id == [u'']:
                response.status = 400
                return u'No domain selected'

            query = {u'concept_id': concept_id, u'domain_id': domain_id}
            json_result = query_cohd_mysql.query_db(service, meta, query)
    else:
        json_result = jsonify([])

    return json_result


if __name__ == u"__main__":
    app.run(host=u'localhost')
