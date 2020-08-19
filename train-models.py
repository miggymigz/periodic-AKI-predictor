from pathlib import Path
from predictor.models import AkiLstm
from sklearn.metrics import roc_auc_score, accuracy_score
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

import fire
import logging
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# setup logging stuff
logging.basicConfig(
    filename='train-models.logs',
    filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    level=logging.DEBUG,
)
logger = logging.getLogger('default')

# set random seed (for reproducibility)
np.random.seed(7)
torch.manual_seed(7)


def train_models(
    epochs: int = 1,
    batch_size: int = 256,
    dataset_dir: str = 'dataset',
    checkpoint_path: str = 'saved_models',
    training: str = 'matrix_training.npy',
    validation: str = 'matrix_validation.npy',
):
    dataset_dir = Path(dataset_dir)
    training_path = dataset_dir / training
    val_path = dataset_dir / validation
    assert training_path.exists(), f'{training} does not exist'
    assert val_path.exists(), f'{validation} does not exist'

    training_matrix = np.load(training_path)
    training_x = torch.tensor(training_matrix[:, :, :-1], dtype=torch.float32)
    training_y = torch.tensor(training_matrix[:, :, -1:], dtype=torch.float32)
    val_matrix = np.load(val_path)
    val_x = torch.tensor(val_matrix[:, :, :-1], dtype=torch.float32)
    val_y = torch.tensor(val_matrix[:, :, -1:], dtype=torch.float32)

    dataset = TensorDataset(training_x, training_y)
    dataloader = DataLoader(
        dataset, batch_size=batch_size,
        shuffle=True, num_workers=4
    )

    model = AkiLstm(timesteps=8, n_features=16)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    loss_obj = torch.nn.BCELoss(reduction='mean')

    for i in range(1, epochs+1):
        e_losses = []
        e_accs = []
        e_scores = []

        pbar = tqdm(dataloader)
        pbar.set_description(f'Epoch {i}/{epochs}')
        for x, y in pbar:
            # set model to training mode
            # also, zero out gradient buffers
            model.train()
            model.zero_grad()

            # compute loss
            y_hat = model(x)
            mask = get_mask_for(x)
            loss = loss_obj(y_hat[mask], y[mask])

            # compute gradients and update model's parameters
            loss.backward()
            optimizer.step()

            # compute accuracy and roc_auc_score for the current batch
            # to be displayed when the current epoch ends
            with torch.no_grad():
                batch_loss = loss.item()
                batch_acc = accuracy_score(y[mask], torch.round(y_hat[mask]))
                batch_score = roc_auc_score(y[mask], y_hat[mask])

                e_losses.append(batch_loss)
                e_accs.append(batch_acc)
                e_scores.append(batch_score)

        # log training statistics after every epoch
        train_loss = torch.tensor(e_losses).mean()
        train_acc = torch.tensor(e_accs).mean()
        train_score = torch.tensor(e_scores).mean()

        # compute statistics with respect to the validation set
        with torch.no_grad():
            model.eval()
            val_y_hat = model(val_x)
            mask = get_mask_for(val_x)
            val_loss = loss_obj(val_y_hat[mask], val_y[mask]).item()
            val_acc = accuracy_score(val_y[mask], torch.round(val_y_hat[mask]))
            val_score = roc_auc_score(val_y[mask], val_y_hat[mask])

        stats_str = f'acc={train_acc:.4f} val_acc={val_acc:.4f} ' + \
            f'roc_auc_score={train_score:.4f} val_roc_auc_score={val_score:.4f} ' + \
            f'loss={train_loss:.4f} val_loss={val_loss:.4f}'
        print(stats_str)
        logger.info(f'Epoch {i}/{epochs}: {stats_str}')

    # ensure checkpoint directory exists
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.mkdir(parents=False, exist_ok=True)

    # save model for later use
    model_path = checkpoint_path / f'e{epochs}_lstm.pt'
    torch.save(model.state_dict(), model_path)


def get_mask_for(x):
    # exclude day 1 and padding days
    mask = x.byte().any(dim=-1).type(torch.bool)
    mask[:, 0] = False
    return mask


if __name__ == '__main__':
    fire.Fire(train_models)
