import json
import sys

# sys.path.insert(0, "./src/")

from absl import app as absl_app
from flask import Flask, Response, current_app, redirect, request

from torchseq.agents.aq_agent import AQAgent

from torchseq.utils.config import Config
from torchseq.utils.tokenizer import Tokenizer


app = Flask(__name__)


@app.route("/")
def index():
    return redirect("/static/demo.htm")


@app.route("/api/generate")
def generate():

    context = request.args["context"]
    answer = request.args["answer"]
    a_pos = context.find(answer)

    query = {"c": context, "a": answer, "a_pos": a_pos}

    res, scores = app.agent.infer(query, reduce_outputs=False)

    scores = scores.tolist()

    output = [list(zip(res[ix], scores[ix])) for ix in range(len(res))]

    return Response(json.dumps(output, indent=2), mimetype="application/json")


@app.route("/api/ping")
def ping():
    return "ack"


def init():

    # MODEL_SLUG = "20200220_161434_bert_embeds_para_pbkagsq_ft_squad"

    # MODEL_PATH = f'./runs/augmented/{MODEL_SLUG}/'
    MODEL_PATH = "./models/optimised/bert_embeds/20200113_075322_0sent_lr3e-3/"

    # Get the config
    with open(MODEL_PATH + "config.json") as f:
        cfg_dict = json.load(f)

    # Override a few bits
    cfg_dict["eval"]["topk"] = 32
    cfg_dict["reranker"] = {
        # 'strategy': 'qa'
        "strategy": None
    }
    cfg_dict["env"]["data_path"] = "./data"

    config = Config(cfg_dict)

    checkpoint_path = MODEL_PATH + "model/checkpoint.pth.tar"

    Tokenizer(config.prepro.tokenizer)

    app.agent = AQAgent(config=config, run_id=None)

    app.agent.load_checkpoint(checkpoint_path)
    app.agent.model.eval()


def main(_):
    init()
    with app.app_context():
        app.run(host="0.0.0.0", port=5004, processes=1)


if __name__ == "__main__":
    absl_app.run(main)